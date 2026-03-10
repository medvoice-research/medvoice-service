"""Patient workflow mapping with SQLite persistence."""

from datetime import datetime
from typing import Optional
from ..config import Config
from .database import (
    store_patient_workflow_db,
    get_patient_by_workflow_db,
    get_workflows_by_patient_hash_db,
    get_patient_name_by_hash_db,
    get_all_patients_db,
    reserve_workflow_mapping_db,
    commit_workflow_mapping_db,
    rollback_workflow_mapping_db,
)


async def store_patient_workflow(
    patient_name: str,
    patient_hash: str,
    workflow_id: str,
    file_path: str,
    department: Optional[str] = None,
    created_by: Optional[str] = None,
):
    """Store patient-workflow mapping."""
    created_at = datetime.now(Config.TIMEZONE).isoformat()
    await store_patient_workflow_db(
        patient_name=patient_name,
        patient_hash=patient_hash,
        workflow_id=workflow_id,
        file_path=file_path,
        department=department,
        created_at=created_at,
        created_by=created_by,
    )


async def get_patient_by_workflow(workflow_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    """Get patient info by workflow ID."""
    return await get_patient_by_workflow_db(workflow_id, user_id=user_id)


async def get_workflows_by_patient_hash(patient_hash: str, user_id: Optional[str] = None) -> list:
    """Get all workflows for a patient by hash."""
    return await get_workflows_by_patient_hash_db(patient_hash, user_id=user_id)


async def get_patient_name_by_hash(patient_hash: str, user_id: Optional[str] = None) -> Optional[str]:
    """Get patient name by hash (admin lookup)."""
    return await get_patient_name_by_hash_db(patient_hash, user_id=user_id)


async def get_all_patients(user_id: Optional[str] = None) -> list:
    """Get all patients with workflow counts."""
    return await get_all_patients_db(user_id=user_id)


# Two-Phase Commit Functions


async def reserve_patient_workflow(
    patient_name: str,
    patient_hash: str,
    workflow_id: str,
    file_path: str,
    department: Optional[str] = None,
    created_by: Optional[str] = None,
):
    """Reserve a patient-workflow mapping with 'pending' status.

    Call this BEFORE starting the Temporal workflow."""
    created_at = datetime.now(Config.TIMEZONE).isoformat()
    await reserve_workflow_mapping_db(
        patient_name=patient_name,
        patient_hash=patient_hash,
        workflow_id=workflow_id,
        file_path=file_path,
        department=department,
        created_at=created_at,
        created_by=created_by,
    )


async def commit_patient_workflow(workflow_id: str):
    """Mark workflow as 'active' after successful start."""
    await commit_workflow_mapping_db(workflow_id)


async def rollback_patient_workflow(workflow_id: str):
    """Delete pending workflow record on failure."""
    await rollback_workflow_mapping_db(workflow_id)
