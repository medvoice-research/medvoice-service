"""Admin endpoints for patient workflow monitoring.

⚠️  SECURITY WARNING - HIPAA COMPLIANCE REQUIRED ⚠️
These endpoints expose Protected Health Information (PHI) including plain text patient names.
Authentication is enforced via AuthMiddleware. Admin endpoints apply user-scoped filtering:
- Administrators see all data (global view)
- Non-admin users see only their own data (+ legacy unowned records)
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from ..logger import logger
from ..auth.dependencies import get_current_user
from ..patients.mapping import get_patient_by_workflow, get_workflows_by_patient_hash, get_patient_name_by_hash


router = APIRouter(prefix="/admin", tags=["Admin"])


def _extract_user_id(current_user: Dict[str, Any]) -> str | None:
    """Return user_id for query scoping; administrators get None (no filter)."""
    if current_user.get("role") == "administrator":
        return None  # Admin sees all data
    return current_user.get("user_id")


@router.get("/patient/hash/{patient_hash}")
async def get_patient_info_by_hash(
    patient_hash: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get patient information by hash (Admin lookup).

    **Purpose:** Admin monitoring - map file/workflow hash back to patient

    **Example:**
    - File: `audio_154c26a1_20251227.mp3`
    - Hash: `154c26a1`
    - Query: `GET /admin/patient/hash/154c26a1`
    - Returns: `{ "patient_name": "John Michael Smith", "workflows": [...] }`"""
    uid = _extract_user_id(current_user)

    # Get patient name from DB (plain text)
    patient_name = await get_patient_name_by_hash(patient_hash, user_id=uid)

    if not patient_name:
        raise HTTPException(status_code=404, detail=f"No patient found with hash: {patient_hash}")

    # Get all workflows for this patient
    workflows = await get_workflows_by_patient_hash(patient_hash, user_id=uid)

    logger.info(f"Admin lookup: patient hash {patient_hash} → {len(workflows)} workflows")

    return {
        "patient_hash": patient_hash,
        "patient_name": patient_name,  # Plain text from DB
        "total_workflows": len(workflows),
        "workflows": workflows,
    }


@router.get("/workflow/{workflow_id}/patient")
async def get_patient_by_workflow_id(
    workflow_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get patient information by workflow ID.

    **Example:**
    - Workflow ID: `whisperx-wf-pt_154c26a1-20251227_145128`
    - Query: `GET /admin/workflow/whisperx-wf-pt_154c26a1-20251227_145128/patient`
    - Returns: `{ "patient_name": "John Michael Smith", ... }`"""
    uid = _extract_user_id(current_user)

    mapping = await get_patient_by_workflow(workflow_id, user_id=uid)

    if not mapping:
        raise HTTPException(status_code=404, detail=f"No patient mapping found for workflow: {workflow_id}")

    logger.info(f"Admin lookup: workflow {workflow_id} → patient {mapping.get('patient_name')}")

    return mapping


@router.get("/patients")
async def list_all_patients(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all patients with workflow counts.

    Administrators see all patients; non-admin users see only their own."""
    uid = _extract_user_id(current_user)

    from ..patients.mapping import get_all_patients

    patients = await get_all_patients(user_id=uid)

    return {"total_patients": len(patients), "patients": patients}


@router.get("/database/stats", tags=["Admin"])
async def get_database_stats(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get real-time database statistics for monitoring.

    Administrators see global stats; non-admin users see only their own.
    """
    from ..patients.database import get_db_connection

    uid = _extract_user_id(current_user)

    async with get_db_connection() as conn:
        if uid is not None:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM patient_workflow_mappings WHERE (created_by = ? OR created_by IS NULL)",
                (uid,),
            )
        else:
            cursor = await conn.execute("SELECT COUNT(*) FROM patient_workflow_mappings")
        row = await cursor.fetchone()
        total_mappings = row[0] if row else 0

        if uid is not None:
            cursor = await conn.execute(
                "SELECT COUNT(DISTINCT patient_hash) FROM patient_workflow_mappings WHERE (created_by = ? OR created_by IS NULL)",
                (uid,),
            )
        else:
            cursor = await conn.execute("SELECT COUNT(DISTINCT patient_hash) FROM patient_workflow_mappings")
        row = await cursor.fetchone()
        unique_patients = row[0] if row else 0

        if uid is not None:
            cursor = await conn.execute("""
                SELECT patient_name, patient_hash, workflow_id, created_at
                FROM patient_workflow_mappings
                WHERE (created_by = ? OR created_by IS NULL)
                ORDER BY created_at DESC
                LIMIT 5
            """, (uid,))
        else:
            cursor = await conn.execute("""
                SELECT patient_name, patient_hash, workflow_id, created_at
                FROM patient_workflow_mappings
                ORDER BY created_at DESC
                LIMIT 5
            """)
        recent = [dict(r) for r in await cursor.fetchall()]

    return {"total_mappings": total_mappings, "unique_patients": unique_patients, "recent_entries": recent}
