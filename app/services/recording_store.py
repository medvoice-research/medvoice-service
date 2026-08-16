"""Local-disk storage for recordings (audio + transcript + medical doc + meta).

Interface is storage-agnostic so MinIO can replace disk later without touching routers.
"""

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Recording IDs are server-generated (`rec_<utc-timestamp>_<hex>`); nothing else is a valid id.
RECORDING_ID_RE = re.compile(r"^rec_[0-9a-f_]+$")


def is_valid_recording_id(recording_id: str) -> bool:
    return bool(recording_id and RECORDING_ID_RE.match(recording_id))


class RecordingStore:
    def __init__(self, storage_dir: str = "./data/recordings"):
        self.storage_dir = Path(storage_dir)

    def _rec_dir(self, recording_id: str) -> Path:
        """Resolved storage dir for a recording, rejecting anything that escapes the store."""
        if not is_valid_recording_id(recording_id):
            raise ValueError(f"invalid recording_id: {recording_id!r}")
        d = (self.storage_dir / recording_id).resolve()
        if not d.is_relative_to(self.storage_dir.resolve()):
            raise ValueError(f"recording_id escapes storage dir: {recording_id!r}")
        return d

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
            "audio_filename": Path(audio_filename).name or "audio",
            "has_medical_document": False,
        }
        self._write_json(d / "meta.json", meta)
        return recording_id

    def audio_path(self, recording_id: str) -> Path:
        meta = self.load_meta(recording_id)
        if not meta:
            raise FileNotFoundError(recording_id)
        return self._rec_dir(recording_id) / (Path(meta.get("audio_filename") or "").name or "audio")

    def save_transcript(self, recording_id: str, transcript: Dict[str, Any]) -> None:
        self._write_json(self._rec_dir(recording_id) / "transcript.json", transcript)

    def save_medical(self, recording_id: str, medical: Dict[str, Any]) -> None:
        self._write_json(self._rec_dir(recording_id) / "medical.json", medical)

    def finalize(self, recording_id: str) -> None:
        meta = self.load_meta(recording_id)
        if not meta:
            raise FileNotFoundError(recording_id)
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
        if not self.storage_dir.exists():
            return []
        items = []
        for d in self.storage_dir.iterdir():
            if not d.is_dir() or not is_valid_recording_id(d.name):
                continue
            meta = self.load_meta(d.name)
            if meta:
                items.append(meta)
        items.sort(key=lambda m: m.get("created_at") or "", reverse=True)
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
