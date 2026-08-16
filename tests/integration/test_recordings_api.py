"""End-to-end: real audio through POST /recordings.

Requires a running server (make up). Medical steps (SOAP/entities/PHI) depend on
LM Studio; the test asserts the transcript path and tolerates empty medical doc.
"""

import os

import httpx
import pytest

BASE = os.getenv("MEDVOICE_TEST_BASE", "http://localhost:8000")
SAMPLE = "datasets/audios/sg/sg-1.WAV"


@pytest.mark.integration
def test_post_recording_end_to_end():
    if not os.path.exists(SAMPLE):
        pytest.skip("sample audio not present (run `make datasets` or keep datasets/audios)")
    with httpx.Client(timeout=360) as client:
        with open(SAMPLE, "rb") as f:
            resp = client.post(
                f"{BASE}/recordings",
                files={"file": ("sg-1.WAV", f, "audio/wav")},
                data={"patient_name": "Integration Test"},
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "completed"
        assert len(body["transcript"]["full_text"]) > 20, "transcript should be non-trivial"
        assert body["has_medical_document"] is True
        assert "soap" in body["medical_document"]
        rid = body["recording_id"]

        lst = client.get(f"{BASE}/recordings").json()
        assert any(r["recording_id"] == rid for r in lst["recordings"])

        detail = client.get(f"{BASE}/recordings/{rid}").json()
        assert detail["transcript"]["full_text"] == body["transcript"]["full_text"]

        assert client.delete(f"{BASE}/recordings/{rid}").status_code == 204
        assert client.get(f"{BASE}/recordings/{rid}").status_code == 404
