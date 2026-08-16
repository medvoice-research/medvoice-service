import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path):
    from app.main import app

    with (
        patch("app.routers.recordings.get_store") as mock_get,
        patch(
            "app.routers.recordings.run_recording_pipeline",
            new=AsyncMock(
                return_value=(
                    {
                        "full_text": "Hello doctor",
                        "segments": [{"speaker": "SPEAKER_01", "start": 0.0, "end": 1.0, "text": "Hello doctor"}],
                    },
                    {
                        "soap": {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"},
                        "entities": [{"name": "Hypertension", "code": "I10", "category": "diagnosis"}],
                        "phi": {"detected": False, "entities": []},
                    },
                )
            ),
        ),
    ):
        store = _FakeStore()
        mock_get.return_value = store
        with TestClient(app) as c:
            yield c, store


class _FakeStore:
    def __init__(self):
        self.recordings = {}

    def create_recording(self, patient_name, language, audio_filename):
        rid = f"rec_test_{len(self.recordings)}"
        self.recordings[rid] = {
            "recording_id": rid,
            "patient_name": patient_name,
            "language": language,
            "status": "processing",
            "audio_filename": audio_filename,
            "created_at": "now",
            "has_medical_document": False,
        }
        return rid

    def audio_path(self, recording_id):
        return "/tmp/fake_audio.m4a"

    def save_transcript(self, recording_id, transcript):
        self.recordings[recording_id]["transcript"] = transcript

    def save_medical(self, recording_id, medical):
        self.recordings[recording_id]["medical"] = medical

    def finalize(self, recording_id):
        self.recordings[recording_id]["status"] = "completed"
        self.recordings[recording_id]["has_medical_document"] = True

    def load_meta(self, recording_id):
        return self.recordings.get(recording_id)

    def load_transcript(self, recording_id):
        return self.recordings.get(recording_id, {}).get("transcript")

    def load_medical(self, recording_id):
        return self.recordings.get(recording_id, {}).get("medical")

    def list_recordings(self):
        return sorted(self.recordings.values(), key=lambda m: m["created_at"], reverse=True)

    def delete_recording(self, recording_id):
        return self.recordings.pop(recording_id, None) is not None


def test_post_recording_returns_full_result(client):
    c, store = client
    resp = c.post(
        "/recordings", files={"file": ("a.m4a", io.BytesIO(b"fake"), "audio/mp4")}, data={"patient_name": "Jane Doe"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["recording_id"].startswith("rec_")
    assert body["status"] == "completed"
    assert body["transcript"]["full_text"] == "Hello doctor"
    assert body["medical_document"]["soap"]["assessment"] == "a"


def test_list_and_get(client):
    c, store = client
    c.post("/recordings", files={"file": ("a.m4a", io.BytesIO(b"fake"), "audio/mp4")})
    lst = c.get("/recordings").json()
    assert len(lst["recordings"]) == 1
    rid = lst["recordings"][0]["recording_id"]
    detail = c.get(f"/recordings/{rid}").json()
    assert detail["transcript"]["full_text"] == "Hello doctor"


def test_delete_and_404(client):
    c, store = client
    c.post("/recordings", files={"file": ("a.m4a", io.BytesIO(b"fake"), "audio/mp4")})
    rid = c.get("/recordings").json()["recordings"][0]["recording_id"]
    assert c.delete(f"/recordings/{rid}").status_code == 204
    assert c.get(f"/recordings/{rid}").status_code == 404
