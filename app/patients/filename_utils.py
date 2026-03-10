"""HIPAA-compliant filename generation utilities.

Generates secure filenames for medical transcription results without
exposing Protected Health Information (PHI).
"""

import hashlib
import uuid
from datetime import datetime
from typing import Optional

from ..config import Config


def generate_patient_file_id(patient_name: str) -> str:
    """Generate short hash from plain text patient name."""
    # Create deterministic hash from patient name + salt
    hash_obj = hashlib.sha256(f"{patient_name}{Config.HIPAA_SALT}".encode())
    return hash_obj.hexdigest()[:8]


def generate_consultation_filename(
    patient_name: str,
    date: Optional[str] = None,
    department: Optional[str] = None,
    sequence: Optional[int] = None,
    extension: str = ".json",
) -> str:
    """Generate HIPAA-compliant filename for consultation transcription.

    Format: pt_{patient_hash}_{date}_{department}_{seq}{extension}
    Example: pt_a7f3c8e2_20251227_cardiology_001.json"""
    patient_hash = generate_patient_file_id(patient_name)

    if date is None:
        date = datetime.now(Config.TIMEZONE).strftime("%Y%m%d")

    # Sanitize department name (remove spaces, special chars)
    if department:
        department = "".join(c for c in department.lower() if c.isalnum() or c == "_")
    else:
        department = "general"

    # Build filename components
    components = [f"pt_{patient_hash}", date, department]

    if sequence is not None:
        components.append(f"{sequence:03d}")

    filename = "_".join(components) + extension
    return filename


def generate_workflow_result_filename(workflow_id: str, extension: str = ".json") -> str:
    """Generate filename based on workflow ID.

    Format: wf_{workflow_id_short}{extension}
    Example: wf_abc123def456.json"""
    # Extract UUID from workflow ID if present
    if "workflow-" in workflow_id:
        wf_uuid = workflow_id.split("workflow-")[-1]
        # Use first 12 chars of UUID
        short_id = wf_uuid.replace("-", "")[:12]
    else:
        short_id = workflow_id[:12]

    return f"wf_{short_id}{extension}"


def generate_anonymous_audio_filename(original_extension: str, patient_name: Optional[str] = None) -> str:
    """Generate anonymous filename for uploaded audio files.

    If patient_name is provided, uses deterministic hash.
    Otherwise, uses random UUID."""
    if patient_name:
        # Deterministic filename for same patient with collision prevention
        patient_hash = generate_patient_file_id(patient_name)
        timestamp = datetime.now(Config.TIMEZONE).strftime("%Y%m%d_%H%M%S%f")
        # Add random suffix to prevent overwrites on concurrent uploads
        random_suffix = uuid.uuid4().hex[:4]
        return f"audio_{patient_hash}_{timestamp}_{random_suffix}{original_extension}"
    else:
        # Random UUID for anonymous uploads
        return f"{uuid.uuid4()}{original_extension}"


def extract_patient_id_from_filename(filename: str) -> Optional[str]:
    """Extract patient hash from HIPAA-compliant filename."""
    if filename.startswith("pt_"):
        parts = filename.split("_")
        if len(parts) >= 2:
            return parts[1]  # patient hash
    return None


def generate_result_storage_path(base_dir: str, patient_name: str, filename: str) -> str:
    """Generate full storage path for result files.

    Organizes files by patient hash subdirectory.
    Format: {base_dir}/{patient_hash[:2]}/{patient_hash}/{filename}"""
    import os

    patient_hash = generate_patient_file_id(patient_name)

    # Use first 2 chars for subdirectory (improves filesystem performance)
    subdir = patient_hash[:2]

    return os.path.join(base_dir, subdir, patient_hash, filename)
