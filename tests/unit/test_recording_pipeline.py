import pytest
from unittest.mock import AsyncMock, patch

from app.services.recording_pipeline import run_recording_pipeline


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
