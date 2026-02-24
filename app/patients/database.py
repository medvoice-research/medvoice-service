"""SQLite database for patient workflow mappings."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import aiosqlite

from ..config import Config
from ..logger import logger


# Database location - use Config for proper path handling
DB_PATH = Path(Config.PATIENT_DB_PATH).resolve()


async def init_database(fresh_start: bool = True):
    """
    Initialize SQLite database with schema.

    Args:
        fresh_start: If True, delete existing database for clean slate
    """
    # Ensure data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Fresh start: delete existing database
    if fresh_start and DB_PATH.exists():
        logger.warning(f"CLEARING DATABASE for fresh start: {DB_PATH}")
        os.remove(DB_PATH)
        logger.info("Database cleared successfully")

    async with aiosqlite.connect(str(DB_PATH)) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")

        # Create patient_workflow_mappings table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS patient_workflow_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_name TEXT NOT NULL,
                patient_hash TEXT NOT NULL,
                workflow_id TEXT NOT NULL UNIQUE,
                file_path TEXT NOT NULL,
                department TEXT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            )
        """)

        # Create index on patient_hash for fast lookups
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_patient_hash
            ON patient_workflow_mappings(patient_hash)
        """)

        # Create index on status for filtering active/pending workflows
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_status
            ON patient_workflow_mappings(status)
        """)

        await conn.commit()

    logger.info(f"SQLite database initialized at {DB_PATH}")


@asynccontextmanager
async def get_db_connection():
    """Async context manager for database connections."""
    conn = await aiosqlite.connect(str(DB_PATH))
    conn.row_factory = aiosqlite.Row  # Return rows as dicts
    try:
        await conn.execute("PRAGMA journal_mode=WAL")
        yield conn
        await conn.commit()
    except Exception as e:
        await conn.rollback()
        logger.error(f"Database error: {str(e)}")
        raise
    finally:
        await conn.close()


async def store_patient_workflow_db(
    patient_name: str,
    patient_hash: str,
    workflow_id: str,
    file_path: str,
    department: Optional[str] = None,
    created_at: Optional[str] = None,
):
    """
    Store patient-workflow mapping in SQLite.

    Args:
        patient_name: Plain text patient name
        patient_hash: 8-char patient hash
        workflow_id: Temporal workflow ID
        file_path: Path to audio file
        department: Optional department name
        created_at: ISO timestamp (auto-generated if None)
    """
    if created_at is None:
        from datetime import datetime

        created_at = datetime.now(Config.TIMEZONE).isoformat()

    async with get_db_connection() as conn:
        await conn.execute(
            """
            INSERT INTO patient_workflow_mappings
            (patient_name, patient_hash, workflow_id, file_path, department, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'active')
        """,
            (patient_name, patient_hash, workflow_id, file_path, department, created_at),
        )

        # Real-time logging
        logger.info(f"DB INSERT: {patient_name} ({patient_hash}) -> {workflow_id}")
        logger.info(f"   File: {file_path}")
        if department:
            logger.info(f"   Department: {department}")

        # Show total count
        count_cursor = await conn.execute("SELECT COUNT(*) FROM patient_workflow_mappings")
        count_row = await count_cursor.fetchone()
        total = count_row[0] if count_row else 0
        logger.info(f"   Total mappings in DB: {total}")


async def reserve_workflow_mapping_db(
    patient_name: str,
    patient_hash: str,
    workflow_id: str,
    file_path: str,
    department: Optional[str] = None,
    created_at: Optional[str] = None,
):
    """
    Reserve a workflow mapping with 'pending' status.

    This creates a database record BEFORE starting the Temporal workflow.
    If the workflow fails to start, call rollback_workflow_mapping_db() to clean up.
    If the workflow starts successfully, call commit_workflow_mapping_db() to mark as active.

    Args:
        patient_name: Plain text patient name
        patient_hash: 8-char patient hash
        workflow_id: Temporal workflow ID
        file_path: Path to audio file
        department: Optional department name
        created_at: ISO timestamp (auto-generated if None)
    """
    if created_at is None:
        from datetime import datetime

        created_at = datetime.now(Config.TIMEZONE).isoformat()

    async with get_db_connection() as conn:
        await conn.execute(
            """
            INSERT INTO patient_workflow_mappings
            (patient_name, patient_hash, workflow_id, file_path, department, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """,
            (patient_name, patient_hash, workflow_id, file_path, department, created_at),
        )

        logger.info(f"DB RESERVE (PENDING): {patient_name} ({patient_hash}) -> {workflow_id}")
        logger.info(f"   File: {file_path}")
        if department:
            logger.info(f"   Department: {department}")


async def commit_workflow_mapping_db(workflow_id: str):
    """
    Mark workflow mapping as 'active'.

    Call this after the Temporal workflow has successfully started.

    Args:
        workflow_id: Workflow ID to commit
    """
    async with get_db_connection() as conn:
        cursor = await conn.execute(
            """
            UPDATE patient_workflow_mappings
            SET status = 'active'
            WHERE workflow_id = ? AND status = 'pending'
        """,
            (workflow_id,),
        )

        if cursor.rowcount == 0:
            logger.warning(f"DB COMMIT: No pending record found for workflow {workflow_id}")
        else:
            logger.info(f"DB COMMIT (ACTIVE): {workflow_id}")


async def rollback_workflow_mapping_db(workflow_id: str):
    """
    Delete pending workflow mapping.

    Call this if the Temporal workflow fails to start, to clean up the pending record.

    Args:
        workflow_id: Workflow ID to rollback
    """
    async with get_db_connection() as conn:
        cursor = await conn.execute(
            """
            DELETE FROM patient_workflow_mappings
            WHERE workflow_id = ? AND status = 'pending'
        """,
            (workflow_id,),
        )

        if cursor.rowcount == 0:
            logger.warning(f"DB ROLLBACK: No pending record found for workflow {workflow_id}")
        else:
            logger.info(f"DB ROLLBACK (DELETED): {workflow_id}")


async def get_patient_by_workflow_db(workflow_id: str) -> Optional[dict]:
    """
    Get patient info by workflow ID from SQLite.

    Args:
        workflow_id: Workflow ID

    Returns:
        Patient mapping dict or None
    """
    async with get_db_connection() as conn:
        cursor = await conn.execute(
            """
            SELECT patient_name, patient_hash, workflow_id, file_path, department, created_at, status
            FROM patient_workflow_mappings
            WHERE workflow_id = ?
        """,
            (workflow_id,),
        )

        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None


async def get_workflows_by_patient_hash_db(patient_hash: str) -> list:
    """
    Get all active workflows for a patient by hash from SQLite.

    Only returns workflows with status='active' (excludes pending/failed).

    Args:
        patient_hash: 8-char patient hash

    Returns:
        List of workflow mapping dicts
    """
    async with get_db_connection() as conn:
        cursor = await conn.execute(
            """
            SELECT patient_name, patient_hash, workflow_id, file_path, department, created_at, status
            FROM patient_workflow_mappings
            WHERE patient_hash = ? AND status = 'active'
            ORDER BY created_at DESC
        """,
            (patient_hash,),
        )

        rows: list = list(await cursor.fetchall())

        # Real-time logging
        logger.info(f"DB QUERY: patient_hash={patient_hash} -> Found {len(rows)} workflows")

        return [dict(row) for row in rows]


async def get_patient_name_by_hash_db(patient_hash: str) -> Optional[str]:
    """
    Get patient name by hash from SQLite.

    Args:
        patient_hash: 8-char patient hash

    Returns:
        Plain text patient name or None
    """
    async with get_db_connection() as conn:
        cursor = await conn.execute(
            """
            SELECT patient_name
            FROM patient_workflow_mappings
            WHERE patient_hash = ?
            LIMIT 1
        """,
            (patient_hash,),
        )

        row = await cursor.fetchone()
        if row:
            return row["patient_name"]
        return None


async def get_all_patients_db() -> list:
    """
    Get summary of all patients with active workflow counts.

    Only counts workflows with status='active' (excludes pending/failed).

    Returns:
        List of patient summaries
    """
    async with get_db_connection() as conn:
        cursor = await conn.execute("""
            SELECT
                patient_hash,
                patient_name,
                COUNT(*) as workflow_count,
                MAX(created_at) as latest_workflow
            FROM patient_workflow_mappings
            WHERE status = 'active'
            GROUP BY patient_hash
            ORDER BY latest_workflow DESC
        """)

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def init_db(fresh_start: bool = False):
    """
    Initialize database. Call this explicitly during application startup.

    Args:
        fresh_start: If True, delete existing database for clean slate
    """
    await init_database(fresh_start=fresh_start)
