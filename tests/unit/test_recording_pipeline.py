import asyncio
import threading

import pytest
from unittest.mock import AsyncMock, patch

from app.services.recording_pipeline import run_recording_pipeline, run_stt


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
        patch("app.services.recording_pipeline.process_audio_file", return_value="audio"),
        patch("app.services.recording_pipeline.transcribe_with_whisper", side_effect=_slow_transcribe),
        patch("app.services.recording_pipeline.diarize", side_effect=RuntimeError("no diarization")),
    ):
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(run_stt(str(audio_file), language="en"), timeout=0.1)
        # Let the abandoned worker exit before the loop's executor is torn down.
        release.set()
        assert finished.wait(10)
        await asyncio.sleep(0.05)
