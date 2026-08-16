"""Recordings API — the mobile-app contract (see docs/superpowers/specs/2026-08-16-mobile-api-contract-design.md)."""

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.config import Config
from app.services.recording_pipeline import run_recording_pipeline
from app.services.recording_store import RecordingStore, is_valid_recording_id

router = APIRouter(tags=["Recordings"])

UPLOAD_CHUNK_BYTES = 1024 * 1024
# Multipart framing sits on top of the file bytes, so an upload exactly at the cap
# declares a slightly larger Content-Length. The streamed byte count is authoritative;
# this only skips reading obviously-oversized bodies.
_MULTIPART_SLACK_BYTES = 8192


class RecordingError(HTTPException):
    """HTTPException carrying the spec's ``error_code``; flattened by the handler in app.main."""

    def __init__(self, status_code: int, detail: str, error_code: str):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


def get_store() -> RecordingStore:
    return RecordingStore(storage_dir=Config.RECORDINGS_STORAGE_DIR)


def _not_found() -> RecordingError:
    return RecordingError(404, "Recording not found", "recording_not_found")


async def _save_upload(file: UploadFile, dest: Path) -> None:
    """Stream the upload to disk, aborting as soon as the running total passes the cap."""
    max_bytes = Config.RECORDINGS_MAX_UPLOAD_BYTES
    total = 0
    with dest.open("wb") as out:
        while chunk := await file.read(UPLOAD_CHUNK_BYTES):
            total += len(chunk)
            if total > max_bytes:
                raise RecordingError(413, "File too large", "file_too_large")
            out.write(chunk)
    if total == 0:
        raise RecordingError(422, "Empty upload", "empty_file")


@router.post("/recordings", status_code=201, summary="Upload audio and process to transcript + medical document")
async def create_recording(
    request: Request,
    file: UploadFile = File(...),
    patient_name: Optional[str] = Form(None),
    language: str = Form("en"),
):
    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in Config.ALLOWED_EXTENSIONS:
        raise RecordingError(415, f"Unsupported file type: {ext}", "unsupported_format")

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > Config.RECORDINGS_MAX_UPLOAD_BYTES + _MULTIPART_SLACK_BYTES:
        raise RecordingError(413, "File too large", "file_too_large")

    store = get_store()
    # The client filename is never used as a path: only its allowlisted extension survives.
    recording_id = store.create_recording(patient_name=patient_name, language=language, audio_filename=f"audio{ext}")
    try:
        audio_path = Path(store.audio_path(recording_id))
        await _save_upload(file, audio_path)

        transcript, medical = await asyncio.wait_for(
            run_recording_pipeline(str(audio_path), language=language),
            timeout=Config.RECORDINGS_SYNC_TIMEOUT_SECONDS,
        )

        store.save_transcript(recording_id, transcript)
        store.save_medical(recording_id, medical)
        store.finalize(recording_id)

        meta = store.load_meta(recording_id)
        return {**meta, "transcript": transcript, "medical_document": medical}
    except Exception as e:
        # Anything past create_recording would otherwise strand a permanent `processing` entry.
        store.delete_recording(recording_id)
        if isinstance(e, RecordingError):
            raise
        if isinstance(e, asyncio.TimeoutError):
            raise RecordingError(504, "Processing timed out", "processing_timeout") from e
        raise RecordingError(500, f"Processing failed: {e}", "processing_failed") from e


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
    if not is_valid_recording_id(recording_id):
        raise _not_found()
    store = get_store()
    meta = store.load_meta(recording_id)
    if not meta:
        raise _not_found()
    return {
        **meta,
        "transcript": store.load_transcript(recording_id) or {"full_text": "", "segments": []},
        "medical_document": store.load_medical(recording_id)
        or {"soap": {}, "entities": [], "phi": {"detected": False, "entities": []}},
    }


@router.delete("/recordings/{recording_id}", status_code=204)
async def delete_recording(recording_id: str):
    if not is_valid_recording_id(recording_id):
        raise _not_found()
    store = get_store()
    if not store.delete_recording(recording_id):
        raise _not_found()
    return Response(status_code=204)
