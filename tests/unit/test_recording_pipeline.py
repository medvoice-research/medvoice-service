import asyncio
import threading

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.recording_pipeline import NoSpeechError, audio_level_dbfs, run_recording_pipeline, run_stt


@pytest.mark.asyncio
async def test_pipeline_full_success(tmp_path):
    audio_file = tmp_path / "a.m4a"
    audio_file.write_bytes(b"fake")

    stt_result = {"segments": [{"speaker": "SPEAKER_01", "start": 0.0, "end": 1.0, "text": "Hello doctor"}]}

    with (
        patch("app.services.recording_pipeline.run_stt", new=AsyncMock(return_value=stt_result)),
        patch(
            "app.services.recording_pipeline.run_medical",
            new=AsyncMock(
                return_value={
                    "soap": {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"},
                    "entities": [{"name": "Hypertension", "code": "I10", "category": "diagnosis"}],
                    "phi": {"detected": False, "entities": []},
                }
            ),
        ),
    ):
        transcript, medical = await run_recording_pipeline(str(audio_file), language="en")

    assert transcript["full_text"] == "Hello doctor"
    assert medical["soap"]["assessment"] == "a"


@pytest.mark.asyncio
async def test_medical_stage_receives_word_segments(tmp_path):
    """TranscriptionTransformer rejects results without word_segments, so the raw
    STT result must reach run_medical while the API transcript stays segments-only."""
    audio_file = tmp_path / "a.m4a"
    audio_file.write_bytes(b"fake")

    stt_result = {
        "segments": [{"speaker": "SPEAKER_01", "start": 0.0, "end": 1.0, "text": "Hello doctor"}],
        "word_segments": [{"word": "Hello", "start": 0.0, "end": 0.5, "speaker": "SPEAKER_01"}],
    }
    medical = AsyncMock(return_value={"soap": {}, "entities": [], "phi": {"detected": False, "entities": []}})

    with (
        patch("app.services.recording_pipeline.run_stt", new=AsyncMock(return_value=stt_result)),
        patch("app.services.recording_pipeline.run_medical", new=medical),
    ):
        transcript, _ = await run_recording_pipeline(str(audio_file), language="en")

    assert medical.await_args.args[0]["word_segments"] == stt_result["word_segments"]
    assert set(transcript) == {"full_text", "segments"}


@pytest.mark.asyncio
async def test_run_stt_does_not_block_the_event_loop(tmp_path):
    """The CPU-bound WhisperX stages must run off-loop so `wait_for` can still fire."""
    audio_file = tmp_path / "a.m4a"
    audio_file.write_bytes(b"fake")
    release, finished = threading.Event(), threading.Event()

    def _slow_transcribe(**kwargs):
        release.wait(10)
        finished.set()
        return {"segments": [], "language": "en"}

    with (
        patch("app.services.recording_pipeline.process_audio_file", return_value=_tone(3.0, 0.5)),
        patch("app.services.recording_pipeline.transcribe_with_whisper", side_effect=_slow_transcribe),
        patch("app.services.recording_pipeline.diarize", side_effect=RuntimeError("no diarization")),
    ):
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(run_stt(str(audio_file), language="en"), timeout=0.1)
        # Let the abandoned worker exit before the loop's executor is torn down.
        release.set()
        assert finished.wait(10)
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "expected"),
    [("vi", "mad1999/pho-whisper-small-ct2"), ("fr", "base")],
)
async def test_run_stt_picks_model_by_language(tmp_path, language, expected):
    """Vietnamese gets its configured model; languages without an entry fall back to WHISPER_MODEL."""
    from app.config import Config

    transcribe = MagicMock(return_value={"segments": [], "language": language})
    with (
        patch.object(Config, "WHISPER_MODELS_BY_LANGUAGE", {"vi": "mad1999/pho-whisper-small-ct2"}),
        patch.object(Config, "WHISPER_MODEL", "base"),
        patch("app.services.recording_pipeline.process_audio_file", return_value=_tone(3.0, 0.5)),
        patch("app.services.recording_pipeline.transcribe_with_whisper", transcribe),
        patch("app.services.recording_pipeline.diarize", side_effect=RuntimeError("no diarization")),
    ):
        await run_stt(str(tmp_path / "a.m4a"), language=language)

    assert transcribe.call_args.kwargs["model"].value == expected


# --- No-speech guard: silent / near-empty audio must never reach the LLM -------------

_SR = 16000


def _stt_patches(audio, transcribe):
    return (
        patch("app.services.recording_pipeline.process_audio_file", return_value=audio),
        patch("app.services.recording_pipeline.transcribe_with_whisper", transcribe),
        patch("app.services.recording_pipeline.diarize", side_effect=RuntimeError("no diarization")),
    )


def _tone(seconds, amplitude):
    t = np.arange(int(seconds * _SR)) / _SR
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


@pytest.mark.asyncio
async def test_regression_digital_silence_is_rejected_before_whisper(tmp_path):
    """-91 dB (all-zero) uploads made Whisper hallucinate "Thank you very much."."""
    transcribe = MagicMock(return_value={"segments": [{"text": "Thank you very much."}], "language": "vi"})
    p1, p2, p3 = _stt_patches(np.zeros(10 * _SR, dtype=np.float32), transcribe)
    with p1, p2, p3, pytest.raises(NoSpeechError, match="silent"):
        await run_stt(str(tmp_path / "a.m4a"), language="vi")
    transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_too_short_recording_is_rejected(tmp_path):
    transcribe = MagicMock(return_value={"segments": [], "language": "vi"})
    p1, p2, p3 = _stt_patches(_tone(0.2, 0.5), transcribe)
    with p1, p2, p3, pytest.raises(NoSpeechError, match="too short"):
        await run_stt(str(tmp_path / "a.m4a"), language="vi")
    transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_quiet_but_real_speech_level_passes_the_guard(tmp_path):
    """-30 dBFS peak is quieter than any real take measured (all >= -24 dBFS)."""
    transcribe = MagicMock(return_value={"segments": [], "language": "vi"})
    p1, p2, p3 = _stt_patches(_tone(3.0, 10 ** (-30 / 20)), transcribe)
    with p1, p2, p3:
        await run_stt(str(tmp_path / "a.m4a"), language="vi")
    transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_empty_transcript_skips_the_medical_llm(tmp_path):
    medical = AsyncMock()
    with (
        patch("app.services.recording_pipeline.run_stt", new=AsyncMock(return_value={"segments": []})),
        patch("app.services.recording_pipeline.run_medical", new=medical),
        pytest.raises(NoSpeechError, match="no words"),
    ):
        await run_recording_pipeline(str(tmp_path / "a.m4a"), language="vi")
    medical.assert_not_called()


def test_audio_level_dbfs():
    assert audio_level_dbfs(np.zeros(100, dtype=np.float32)) <= -90
    assert audio_level_dbfs(np.array([], dtype=np.float32)) <= -90
    assert abs(audio_level_dbfs(_tone(1.0, 0.5)) - (-6.02)) < 0.1
