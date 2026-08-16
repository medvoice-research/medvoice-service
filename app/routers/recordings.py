"""Recordings API — the mobile-app contract (see docs/superpowers/specs/2026-08-16-mobile-api-contract-design.md)."""

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.config import Config
from app.services.recording_pipeline import run_recording_pipeline
from app.services.recording_store import RecordingStore

router = APIRouter(tags=["Recordings"])


def get_store() -> RecordingStore:
    return RecordingStore(storage_dir=Config.RECORDINGS_STORAGE_DIR)


@router.post("/recordings", status_code=201, summary="Upload audio and process to transcript + medical document")
async def create_recording(
    file: UploadFile = File(...),
    patient_name: Optional[str] = Form(None),
    language: str = Form("en"),
):
    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in Config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415, detail={"detail": f"Unsupported file type: {ext}", "error_code": "unsupported_format"}
        )

    store = get_store()
    recording_id = store.create_recording(
        patient_name=patient_name, language=language, audio_filename=file.filename or "audio"
    )
    audio_path = Path(store.audio_path(recording_id))
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
        raise HTTPException(
            status_code=504, detail={"detail": "Processing timed out", "error_code": "processing_timeout"}
        )
    except Exception as e:
        store.delete_recording(recording_id)
        raise HTTPException(
            status_code=500, detail={"detail": f"Processing failed: {e}", "error_code": "processing_failed"}
        )

    store.save_transcript(recording_id, transcript)
    store.save_medical(recording_id, medical)
    store.finalize(recording_id)

    meta = store.load_meta(recording_id)
    return {**meta, "transcript": transcript, "medical_document": medical}


@router.get("/recordings", summary="List recordings (newest first)")
async def list_recordings():
    store = get_store()
    items = store.list_recordings()
    return {
        "recordings": [
            {k: m.get(k) for k in ("recording_id", "patient_name", "created_at", "status", "has_medical_document")}
            for m in items
        ]
    }


@router.get("/recordings/{recording_id}", summary="Get recording detail")
async def get_recording(recording_id: str):
    store = get_store()
    meta = store.load_meta(recording_id)
    if not meta:
        raise HTTPException(
            status_code=404, detail={"detail": "Recording not found", "error_code": "recording_not_found"}
        )
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
        raise HTTPException(
            status_code=404, detail={"detail": "Recording not found", "error_code": "recording_not_found"}
        )
    return Response(status_code=204)
