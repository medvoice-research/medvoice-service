import asyncio
import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import Config

_TRANSCRIPT = {
    "full_text": "Hello doctor",
    "segments": [{"speaker": "SPEAKER_01", "start": 0.0, "end": 1.0, "text": "Hello doctor"}],
}
_MEDICAL = {
    "soap": {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"},
    "entities": [{"name": "Hypertension", "code": "I10", "category": "diagnosis"}],
    "phi": {"detected": False, "entities": []},
}


@pytest.fixture()
def client(tmp_path):
    from app.main import app

    with (
        patch("app.routers.recordings.get_store") as mock_get,
        patch("app.routers.recordings.run_recording_pipeline", new=AsyncMock(return_value=(_TRANSCRIPT, _MEDICAL))),
    ):
        store = _FakeStore(tmp_path)
        mock_get.return_value = store
        with TestClient(app) as c:
            yield c, store


@pytest.fixture()
def real_client(tmp_path):
    """Client backed by the real RecordingStore, for filesystem-containment tests."""
    from app.main import app

    storage = tmp_path / "storage"
    with (
        patch.object(Config, "RECORDINGS_STORAGE_DIR", str(storage)),
        patch("app.routers.recordings.run_recording_pipeline", new=AsyncMock(return_value=(_TRANSCRIPT, _MEDICAL))),
    ):
        with TestClient(app) as c:
            yield c, storage



class _FakeStore:
    def __init__(self, tmp_path):
        self.recordings = {}
        self.audio_dir = Path(tmp_path) / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def create_recording(self, patient_name, language, audio_filename):
        rid = f"rec_20260101_000000_{len(self.recordings):08x}"
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
        return self.audio_dir / f"{recording_id}.m4a"

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


def _assert_flat_envelope(resp, status_code, error_code):
    assert resp.status_code == status_code
    body = resp.json()
    assert set(body) == {"detail", "error_code"}, body
    assert body["error_code"] == error_code
    assert isinstance(body["detail"], str)


def test_unsupported_format_returns_flat_415(client):
    c, store = client
    resp = c.post("/recordings", files={"file": ("a.exe", io.BytesIO(b"fake"), "application/octet-stream")})
    _assert_flat_envelope(resp, 415, "unsupported_format")
    assert store.recordings == {}


def test_oversized_upload_returns_413_and_leaves_no_orphan(client):
    c, store = client
    with patch.object(Config, "RECORDINGS_MAX_UPLOAD_BYTES", 16):
        resp = c.post("/recordings", files={"file": ("a.m4a", io.BytesIO(b"x" * 4096), "audio/mp4")})
    _assert_flat_envelope(resp, 413, "file_too_large")
    assert store.recordings == {}


def test_empty_upload_returns_422(client):
    c, store = client
    resp = c.post("/recordings", files={"file": ("a.m4a", io.BytesIO(b""), "audio/mp4")})
    _assert_flat_envelope(resp, 422, "empty_file")
    assert store.recordings == {}


def test_pipeline_timeout_returns_504_and_leaves_no_orphan(client):
    c, store = client

    async def _slow(*args, **kwargs):
        await asyncio.sleep(5)

    with (
        patch("app.routers.recordings.run_recording_pipeline", new=_slow),
        patch.object(Config, "RECORDINGS_SYNC_TIMEOUT_SECONDS", 0.05),
    ):
        resp = c.post("/recordings", files={"file": ("a.m4a", io.BytesIO(b"fake"), "audio/mp4")})
    _assert_flat_envelope(resp, 504, "processing_timeout")
    assert store.recordings == {}


def test_pipeline_failure_returns_500_and_leaves_no_orphan(client):
    c, store = client
    with patch("app.routers.recordings.run_recording_pipeline", new=AsyncMock(side_effect=RuntimeError("boom"))):
        resp = c.post("/recordings", files={"file": ("a.m4a", io.BytesIO(b"fake"), "audio/mp4")})
    _assert_flat_envelope(resp, 500, "processing_failed")
    assert store.recordings == {}


def test_store_failure_after_pipeline_leaves_no_orphan(client):
    """Persistence errors must not strand a permanent `processing` phantom."""
    c, store = client

    def _boom(recording_id, transcript):
        raise OSError("disk full")

    store.save_transcript = _boom
    resp = c.post("/recordings", files={"file": ("a.m4a", io.BytesIO(b"fake"), "audio/mp4")})
    _assert_flat_envelope(resp, 500, "processing_failed")
    assert store.recordings == {}


def test_not_found_uses_flat_envelope(client):
    c, store = client
    _assert_flat_envelope(c.get("/recordings/rec_20260101_000000_deadbeef"), 404, "recording_not_found")
    _assert_flat_envelope(c.delete("/recordings/rec_20260101_000000_deadbeef"), 404, "recording_not_found")


@pytest.mark.parametrize("rid", ["%2e%2e", "rec_../../evil", "rec_%2e%2e"])
def test_traversal_recording_id_is_rejected(client, rid):
    c, store = client
    _assert_flat_envelope(c.get(f"/recordings/{rid}"), 404, "recording_not_found")
    _assert_flat_envelope(c.delete(f"/recordings/{rid}"), 404, "recording_not_found")


def test_encoded_slash_traversal_never_reaches_the_endpoint(client):
    """`%2f` decodes to a separator, so the path no longer matches the route at all."""
    c, store = client
    assert c.get("/recordings/..%2f..%2fevil").status_code == 404
    assert c.delete("/recordings/..%2f..%2fevil").status_code == 404


def test_delete_traversal_does_not_wipe_the_storage_tree(real_client):
    c, storage = real_client
    c.post("/recordings", files={"file": ("a.m4a", io.BytesIO(b"fake"), "audio/mp4")})
    assert c.delete("/recordings/%2e%2e").status_code == 404
    assert c.delete("/recordings/..%2f..%2fevil").status_code == 404
    assert storage.exists()
    assert len(c.get("/recordings").json()["recordings"]) == 1


def test_upload_filename_traversal_stays_inside_storage(real_client):
    c, storage = real_client
    resp = c.post("/recordings", files={"file": ("../../../evil.mp4", io.BytesIO(b"PWNED"), "video/mp4")})
    assert resp.status_code == 201
    rid = resp.json()["recording_id"]
    assert list(storage.parent.rglob("evil.mp4")) == []
    assert (storage / rid / "audio.mp4").read_bytes() == b"PWNED"


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
