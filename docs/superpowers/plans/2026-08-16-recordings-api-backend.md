# Recordings API (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a synchronous `/recordings` API to medvoice-service: multipart upload -> WhisperX STT -> medical document (SOAP + ICD-10 entities + PHI) -> stored result, plus list/get/delete. This is the contract the Flutter app will call.

**Architecture:** New router `app/routers/recordings.py` + storage abstraction `app/services/recording_store.py`. POST /recordings saves the upload, runs the pipeline synchronously (reusing `app/whisperx_services.py` transcribe/align/diarize and `app/llm/medical_llm_service.py`), persists transcript.json/medical.json/meta.json under `./data/recordings/{id}/`, returns the full result inline. Temporal is NOT in this path (nice-to-have only). Config under `recordings:` in config.yaml.

**Tech Stack:** FastAPI, WhisperX (already in repo), medical_llm_service (already in repo), pytest + httpx TestClient. Python 3.11, uv. Spec: docs/superpowers/specs/2026-08-16-mobile-api-contract-design.md

---

### Task 1: RecordingStore — storage abstraction

**Files:**
- Create: `app/services/recording_store.py`
- Test: `tests/unit/test_recording_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_recording_store.py
import json
import os
import pytest
from app.services.recording_store import RecordingStore


@pytest.fixture()
def store(tmp_path):
    return RecordingStore(storage_dir=str(tmp_path))


def test_save_and_load_recording(store):
    rec_id = store.create_recording(patient_name="Jane Doe", language="en", audio_filename="a.m4a")
    assert rec_id.startswith("rec_")
    audio_path = store.audio_path(rec_id)
    with open(audio_path, "w") as f:
        f.write("fake-audio")
    store.save_transcript(rec_id, {"full_text": "hi", "segments": []})
    store.save_medical(rec_id, {"soap": {}, "entities": [], "phi": {"detected": False, "entities": []}})
    store.finalize(rec_id)

    meta = store.load_meta(rec_id)
    assert meta["status"] == "completed"
    assert store.load_transcript(rec_id)["full_text"] == "hi"
    assert os.path.exists(store.audio_path(rec_id))


def test_list_recordings_newest_first(store):
    a = store.create_recording(patient_name="A", language="en", audio_filename="a.m4a")
    b = store.create_recording(patient_name="B", language="en", audio_filename="b.m4a")
    for rid in (a, b):
        store.finalize(rid)
    items = store.list_recordings()
    assert [i["recording_id"] for i in items] == [b, a]


def test_delete_recording(store):
    rid = store.create_recording(patient_name="A", language="en", audio_filename="a.m4a")
    store.finalize(rid)
    assert store.delete_recording(rid) is True
    assert store.load_meta(rid) is None
    assert store.delete_recording(rid) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_recording_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.recording_store'`

- [ ] **Step 3: Implement RecordingStore**

```python
# app/services/recording_store.py
"""Local-disk storage for recordings (audio + transcript + medical doc + meta).

Interface is storage-agnostic so MinIO can replace disk later without touching routers.
"""
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class RecordingStore:
    def __init__(self, storage_dir: str = "./data/recordings"):
        self.storage_dir = Path(storage_dir)

    def _rec_dir(self, recording_id: str) -> Path:
        return self.storage_dir / recording_id

    def create_recording(self, patient_name: Optional[str], language: str, audio_filename: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        recording_id = f"rec_{ts}_{uuid.uuid4().hex[:8]}"
        d = self._rec_dir(recording_id)
        d.mkdir(parents=True, exist_ok=True)
        meta = {
            "recording_id": recording_id,
            "patient_name": patient_name,
            "language": language,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "processing",
            "audio_filename": audio_filename,
            "has_medical_document": False,
        }
        self._write_json(d / "meta.json", meta)
        return recording_id

    def audio_path(self, recording_id: str) -> Path:
        meta = self.load_meta(recording_id)
        if not meta:
            raise FileNotFoundError(recording_id)
        return self._rec_dir(recording_id) / meta["audio_filename"]

    def save_transcript(self, recording_id: str, transcript: Dict[str, Any]) -> None:
        self._write_json(self._rec_dir(recording_id) / "transcript.json", transcript)

    def save_medical(self, recording_id: str, medical: Dict[str, Any]) -> None:
        self._write_json(self._rec_dir(recording_id) / "medical.json", medical)

    def finalize(self, recording_id: str) -> None:
        meta = self.load_meta(recording_id)
        meta["status"] = "completed"
        meta["has_medical_document"] = (self._rec_dir(recording_id) / "medical.json").exists()
        self._write_json(self._rec_dir(recording_id) / "meta.json", meta)

    def load_meta(self, recording_id: str) -> Optional[Dict[str, Any]]:
        p = self._rec_dir(recording_id) / "meta.json"
        return self._read_json(p) if p.exists() else None

    def load_transcript(self, recording_id: str) -> Optional[Dict[str, Any]]:
        p = self._rec_dir(recording_id) / "transcript.json"
        return self._read_json(p) if p.exists() else None

    def load_medical(self, recording_id: str) -> Optional[Dict[str, Any]]:
        p = self._rec_dir(recording_id) / "medical.json"
        return self._read_json(p) if p.exists() else None

    def list_recordings(self) -> List[Dict[str, Any]]:
        items = []
        for d in self.storage_dir.iterdir():
            if not d.is_dir():
                continue
            meta = self.load_meta(d.name)
            if meta:
                items.append(meta)
        items.sort(key=lambda m: m["created_at"], reverse=True)
        return items

    def delete_recording(self, recording_id: str) -> bool:
        d = self._rec_dir(recording_id)
        if not d.exists():
            return False
        shutil.rmtree(d)
        return True

    @staticmethod
    def _write_json(path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_recording_store.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/recording_store.py tests/unit/test_recording_store.py
git commit -m "feat: add RecordingStore local-disk storage layer"
```

---

### Task 2: Pipeline service — run STT + medical synchronously

**Files:**
- Create: `app/services/recording_pipeline.py`
- Test: `tests/unit/test_recording_pipeline.py`

- [ ] **Step 1: Write the failing test (pipeline orchestrates mocked steps)**

```python
# tests/unit/test_recording_pipeline.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.recording_pipeline import run_recording_pipeline


@pytest.mark.asyncio
async def test_pipeline_full_success(tmp_path):
    audio_file = tmp_path / "a.m4a"
    audio_file.write_bytes(b"fake")

    stt_result = {
        "segments": [
            {"speaker": "SPEAKER_01", "start": 0.0, "end": 1.0, "text": "Hello doctor"}
        ]
    }

    with patch("app.services.recording_pipeline.run_stt", new=AsyncMock(return_value=stt_result)), \
         patch("app.services.recording_pipeline.run_medical", new=AsyncMock(return_value={
             "soap": {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"},
             "entities": [{"name": "Hypertension", "code": "I10", "category": "diagnosis"}],
             "phi": {"detected": False, "entities": []},
         })):
        transcript, medical = await run_recording_pipeline(str(audio_file), language="en")

    assert transcript["full_text"] == "Hello doctor"
    assert medical["soap"]["assessment"] == "a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_recording_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.recording_pipeline'`

- [ ] **Step 3: Implement pipeline service**

Read `app/temporal/activities.py` first — reuse the exact call patterns (`process_audio_file`, `transcribe_with_whisper`, `align_whisper_output`, `diarize`). Read `app/routers/medical.py` `process_transcript` (line ~595), `app/services/transcription_transformer.py`, and `app/llm/medical_llm_service.py` for the medical steps.

```python
# app/services/recording_pipeline.py
"""Synchronous pipeline: audio file -> transcript + medical document.

Reuses the same WhisperX functions the Temporal activities call, plus the
medical LLM service, but runs inline (no Temporal dependency).
"""
from typing import Any, Dict, Tuple

from app.audio import process_audio_file
from app.schemas import WhisperModelParams, ASROptions, VADOptions, AlignmentParams, DiarizationParams
from app.whisperx_services import transcribe_with_whisper, align_whisper_output, diarize


async def run_stt(audio_path: str, language: str = "en", model: str = "base") -> Dict[str, Any]:
    audio = process_audio_file(audio_path)
    mp = WhisperModelParams(language=language, model=model)
    result = transcribe_with_whisper(
        audio=audio,
        task=mp.task.value,
        asr_options=ASROptions().model_dump(),
        vad_options=VADOptions().model_dump(),
        language=mp.language,
        batch_size=mp.batch_size,
        chunk_size=mp.chunk_size,
        model=mp.model,
        device=mp.device.value if hasattr(mp.device, "value") else str(mp.device),
        device_index=mp.device_index,
        compute_type=mp.compute_type,
        threads=mp.threads,
    )
    if result.get("segments"):
        ap = AlignmentParams()
        result = align_whisper_output(
            transcript=result["segments"],
            audio=audio,
            language_code=result.get("language", language),
            device=ap.device.value if hasattr(ap.device, "value") else str(ap.device),
            align_model=ap.align_model,
            interpolate_method=ap.interpolate_method.value if hasattr(ap.interpolate_method, "value") else ap.interpolate_method,
            return_char_alignments=ap.return_char_alignments,
        )
    try:
        dp = DiarizationParams()
        diarized = diarize(
            audio,
            device=dp.device.value if hasattr(dp.device, "value") else str(dp.device),
            min_speakers=dp.min_speakers,
            max_speakers=dp.max_speakers,
        )
        speaker_map = {}
        if diarized and diarized.get("segments"):
            for seg in diarized["segments"]:
                for i in range(int(seg["start"] * 100), int(seg["end"] * 100)):
                    speaker_map[i] = seg["speaker"]
            for seg in result.get("segments", []):
                key = int((seg["start"] + seg["end"]) / 2 * 100)
                seg["speaker"] = speaker_map.get(key, "SPEAKER_00")
    except Exception:
        for seg in result.get("segments", []):
            seg.setdefault("speaker", "SPEAKER_00")

    full_text = " ".join(s["text"].strip() for s in result.get("segments", []) if s.get("text"))
    return {"full_text": full_text, "segments": result.get("segments", [])}


async def run_medical(transcript: Dict[str, Any]) -> Dict[str, Any]:
    """PHI + entities + SOAP via the existing medical LLM service. Degrades per-step."""
    from app.llm.medical_llm_service import MedicalLLMService
    from app.services.transcription_transformer import TranscriptionTransformer

    service = MedicalLLMService()
    result: Dict[str, Any] = {"soap": {}, "entities": [], "phi": {"detected": False, "entities": []}}

    try:
        dialogue = TranscriptionTransformer().transform({"segments": transcript.get("segments", [])})
    except Exception:
        dialogue = {"dialogue": [{"speaker": "unknown", "text": transcript.get("full_text", "")}], "speaker_mapping": {}}

    try:
        phi = await service.detect_phi_in_dialogue(dialogue)
        result["phi"] = {"detected": bool(phi.get("phi_detected")), "entities": phi.get("entities", [])}
    except Exception:
        pass
    try:
        entities = await service.extract_entities_with_speaker(dialogue)
        result["entities"] = entities or []
    except Exception:
        pass
    try:
        soap = await service.generate_soap_from_dialogue(dialogue)
        if isinstance(soap, dict):
            result["soap"] = {
                "subjective": soap.get("subjective", ""),
                "objective": soap.get("objective", ""),
                "assessment": soap.get("assessment", ""),
                "plan": soap.get("plan", ""),
            }
    except Exception:
        pass
    return result


async def run_recording_pipeline(audio_path: str, language: str = "en") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    transcript = await run_stt(audio_path, language=language)
    medical = await run_medical(transcript)
    return transcript, medical
```

- [ ] **Step 4: Verify signatures against the real code before running**

Run: `uv run python -c "from app.whisperx_services import transcribe_with_whisper, align_whisper_output, diarize; import inspect; print(inspect.signature(transcribe_with_whisper)); print(inspect.signature(align_whisper_output)); print(inspect.signature(diarize))"`
If any signature differs from the calls above (parameter names like `model`, `asr_options`, `vad_options`, `transcript`), adjust the pipeline calls to match — the unit tests mock these functions so they will still pass, but the integration test in Task 4 will catch real mismatches.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_recording_pipeline.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/recording_pipeline.py tests/unit/test_recording_pipeline.py
git commit -m "feat: add synchronous STT + medical recording pipeline"
```

---

### Task 3: Recordings router

**Files:**
- Create: `app/routers/recordings.py`
- Modify: `app/main.py` (register router)
- Modify: `config.yaml` (recordings section), `app/config.py` (Config attrs)
- Test: `tests/unit/test_recordings_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_recordings_router.py
import io
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


@pytest.fixture()
def client(tmp_path):
    from app.main import app
    with patch("app.routers.recordings.get_store") as mock_get, \
         patch("app.routers.recordings.run_recording_pipeline", new=AsyncMock(return_value=(
             {"full_text": "Hello doctor", "segments": [{"speaker": "SPEAKER_01", "start": 0.0, "end": 1.0, "text": "Hello doctor"}]},
             {"soap": {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"},
              "entities": [{"name": "Hypertension", "code": "I10", "category": "diagnosis"}],
              "phi": {"detected": False, "entities": []}},
         ))):
        store = _FakeStore()
        mock_get.return_value = store
        with TestClient(app) as c:
            yield c, store


class _FakeStore:
    def __init__(self):
        self.recordings = {}

    def create_recording(self, patient_name, language, audio_filename):
        rid = f"rec_test_{len(self.recordings)}"
        self.recordings[rid] = {"recording_id": rid, "patient_name": patient_name,
                                "language": language, "status": "processing",
                                "audio_filename": audio_filename, "created_at": "now",
                                "has_medical_document": False}
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
    resp = c.post("/recordings", files={"file": ("a.m4a", io.BytesIO(b"fake"), "audio/mp4")},
                  data={"patient_name": "Jane Doe"})
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_recordings_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routers.recordings'`

- [ ] **Step 3: Implement the router**

```python
# app/routers/recordings.py
"""Recordings API — the mobile-app contract (see docs/superpowers/specs/2026-08-16-mobile-api-contract-design.md)."""
import asyncio
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.config import Config
from app.services.recording_pipeline import run_recording_pipeline
from app.services.recording_store import RecordingStore

router = APIRouter(tags=["Recordings"])

_SUPPORTED_EXT = {".oga", ".m4a", ".aac", ".wav", ".amr", ".wma", ".awb", ".mp3", ".ogg",
                  ".wmv", ".mkv", ".avi", ".mov", ".mp4"}


def get_store() -> RecordingStore:
    return RecordingStore(storage_dir=Config.RECORDINGS_STORAGE_DIR)


@router.post("/recordings", status_code=201, summary="Upload audio and process to transcript + medical document")
async def create_recording(
    file: UploadFile = File(...),
    patient_name: Optional[str] = Form(None),
    language: str = Form("en"),
):
    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in _SUPPORTED_EXT:
        raise HTTPException(status_code=415, detail={"detail": f"Unsupported file type: {ext}", "error_code": "unsupported_format"})

    store = get_store()
    recording_id = store.create_recording(patient_name=patient_name, language=language, audio_filename=file.filename or "audio")
    audio_path = store.audio_path(recording_id)
    content = await file.read()
    if len(content) > Config.RECORDINGS_MAX_UPLOAD_BYTES:
        store.delete_recording(recording_id)
        raise HTTPException(status_code=413, detail={"detail": "File too large", "error_code": "file_too_large"})
    audio_path.write_bytes(content)

    try:
        transcript, medical = await asyncio.wait_for(
            run_recording_pipeline(str(audio_path), language=language),
            timeout=Config.RECORDINGS_SYNC_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        store.delete_recording(recording_id)
        raise HTTPException(status_code=504, detail={"detail": "Processing timed out", "error_code": "processing_timeout"})
    except Exception as e:
        store.delete_recording(recording_id)
        raise HTTPException(status_code=500, detail={"detail": f"Processing failed: {e}", "error_code": "processing_failed"})

    store.save_transcript(recording_id, transcript)
    store.save_medical(recording_id, medical)
    store.finalize(recording_id)

    meta = store.load_meta(recording_id)
    return {**meta, "transcript": transcript, "medical_document": medical}


@router.get("/recordings", summary="List recordings (newest first)")
async def list_recordings():
    store = get_store()
    items = store.list_recordings()
    return {"recordings": [
        {k: m.get(k) for k in ("recording_id", "patient_name", "created_at", "status", "has_medical_document")}
        for m in items
    ]}


@router.get("/recordings/{recording_id}", summary="Get recording detail")
async def get_recording(recording_id: str):
    store = get_store()
    meta = store.load_meta(recording_id)
    if not meta:
        raise HTTPException(status_code=404, detail={"detail": "Recording not found", "error_code": "recording_not_found"})
    return {
        **meta,
        "transcript": store.load_transcript(recording_id) or {"full_text": "", "segments": []},
        "medical_document": store.load_medical(recording_id)
        or {"soap": {}, "entities": [], "phi": {"detected": False, "entities": []}},
    }


@router.delete("/recordings/{recording_id}", status_code=204)
async def delete_recording(recording_id: str):
    store = get_store()
    if not store.delete_recording(recording_id):
        raise HTTPException(status_code=404, detail={"detail": "Recording not found", "error_code": "recording_not_found"})
    return Response(status_code=204)
```

- [ ] **Step 4: Register the router and config**

Modify `app/main.py` — add to the import block (line ~17):
```python
from .routers import recordings
```
And after the other include_router lines (after line ~220):
```python
app.include_router(recordings.router)
```

Add to `config.yaml`:
```yaml
# Recordings API
recordings:
  storage_dir: ./data/recordings
  sync_timeout_seconds: 300
  max_upload_mb: 200
```

Add to `app/config.py` Config class (near the other YAML-backed attrs):
```python
    RECORDINGS_STORAGE_DIR = _get_yaml_nested("recordings", "storage_dir", "./data/recordings")
    RECORDINGS_SYNC_TIMEOUT_SECONDS = int(_get_yaml_nested("recordings", "sync_timeout_seconds", 300))
    RECORDINGS_MAX_UPLOAD_BYTES = int(_get_yaml_nested("recordings", "max_upload_mb", 200)) * 1024 * 1024
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_recordings_router.py -v`
Expected: PASS (4 tests). If TestClient import of app.main fails due to Temporal/LM Studio startup, mock `temporal_manager.get_client` in the fixture the same way tests/integration tests do (check tests/conftest.py for the established pattern).

- [ ] **Step 6: Commit**

```bash
git add app/routers/recordings.py app/main.py config.yaml app/config.py tests/unit/test_recordings_router.py
git commit -m "feat: add recordings API (POST/GET/DELETE) with sync pipeline"
```

---

### Task 4: Integration test with real audio

**Files:**
- Create: `tests/integration/test_recordings_api.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_recordings_api.py
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
        assert body["medical_document"]["soap"] != {}
        rid = body["recording_id"]

        lst = client.get(f"{BASE}/recordings").json()
        assert any(r["recording_id"] == rid for r in lst["recordings"])

        detail = client.get(f"{BASE}/recordings/{rid}").json()
        assert detail["transcript"]["full_text"] == body["transcript"]["full_text"]

        assert client.delete(f"{BASE}/recordings/{rid}").status_code == 204
        assert client.get(f"{BASE}/recordings/{rid}").status_code == 404
```

- [ ] **Step 2: Run lint + all unit tests**

Run: `uv run ruff check app/ tests/ streamlit_app/ --config pyproject.toml`
Run: `uv run pytest tests/unit/ -v`
Expected: lint clean, all unit tests pass (existing 197 + new ones)

- [ ] **Step 3: Run the integration test against the live stack**

Run: `uv run pytest tests/integration/test_recordings_api.py -v -m integration`
Expected: PASS (server must be up; LM Studio optional — SOAP may be empty dict if absent, adjust assertion in Step 1 to tolerate empty soap when LM Studio is down, but keep `has_medical_document` and transcript assertions strict).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_recordings_api.py
git commit -m "test: add end-to-end recordings API integration test"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README API section**

In README.md under "## API Endpoints", add a "### Recordings (mobile app contract)" section listing the 4 endpoints with the request/response summary from the spec, and note: "Synchronous processing; Temporal not required for this path."

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document recordings API in README"
```
