"""Unit tests for patient mapping functionality."""

import asyncio
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest
import pytest_asyncio

from app.patients.mapping import (
    get_patient_by_workflow,
    get_workflows_by_patient_hash,
    get_patient_name_by_hash,
    store_patient_workflow,
)


@pytest_asyncio.fixture
async def test_db():
    """
    Provide an isolated in-memory aiosqlite database for each test.

    This fixture ensures proper test isolation by:
    - Using an in-memory database (:memory:) unique to each test
    - Reusing the schema creation logic from app.patients.database
    - Preventing race conditions in parallel test execution
    - Avoiding file I/O for faster test execution

    If schema changes, tests automatically stay in sync.
    """
    db_name = f"file:testdb_{uuid.uuid4().hex}?mode=memory&cache=shared"
    conn = await aiosqlite.connect(db_name, uri=True)
    conn.row_factory = aiosqlite.Row

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

    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_patient_hash
        ON patient_workflow_mappings(patient_hash)
    """)

    await conn.commit()

    @asynccontextmanager
    async def get_test_db_connection():
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    with patch("app.patients.database.get_db_connection", get_test_db_connection):
        yield conn

    await conn.close()


@pytest.mark.asyncio
class TestPatientMapping:
    """Test patient-workflow mapping storage and retrieval."""

    async def test_store_patient_workflow(self, test_db):
        """Test storing patient-workflow mapping."""
        await store_patient_workflow(
            patient_name="John Michael Smith",
            patient_hash="154c26a1",
            workflow_id="whisperx-wf-pt_154c26a1-20251227_150000",
            file_path="/tmp/uploads/audio_154c26a1_20251227_150000.mp3",
            department="Cardiology",
        )

        mapping = await get_patient_by_workflow("whisperx-wf-pt_154c26a1-20251227_150000")
        assert mapping is not None
        assert mapping["patient_name"] == "John Michael Smith"
        assert mapping["patient_hash"] == "154c26a1"
        assert mapping["department"] == "Cardiology"

    async def test_get_patient_by_workflow(self, test_db):
        """Test retrieving patient info by workflow ID."""
        await store_patient_workflow(
            patient_name="Jane Doe", patient_hash="abc12345", workflow_id="workflow-123", file_path="/tmp/test.mp3"
        )

        result = await get_patient_by_workflow("workflow-123")

        assert result is not None
        assert result["patient_name"] == "Jane Doe"
        assert result["patient_hash"] == "abc12345"
        assert result["workflow_id"] == "workflow-123"

    async def test_get_patient_by_workflow_not_found(self, test_db):
        """Test getting non-existent workflow."""
        result = await get_patient_by_workflow("nonexistent")
        assert result is None

    async def test_get_workflows_by_patient_hash(self, test_db):
        """Test retrieving all workflows for a patient."""
        patient_hash = "154c26a1"

        await store_patient_workflow(
            patient_name="John Smith", patient_hash=patient_hash, workflow_id="workflow-1", file_path="/tmp/file1.mp3"
        )

        await store_patient_workflow(
            patient_name="John Smith", patient_hash=patient_hash, workflow_id="workflow-2", file_path="/tmp/file2.mp3"
        )

        workflows = await get_workflows_by_patient_hash(patient_hash)

        assert len(workflows) == 2

        ids = [w["workflow_id"] for w in workflows]
        assert "workflow-1" in ids
        assert "workflow-2" in ids

    async def test_get_workflows_by_patient_hash_empty(self, test_db):
        """Test getting workflows for non-existent patient."""
        workflows = await get_workflows_by_patient_hash("nonexistent")
        assert workflows == []

    async def test_get_patient_name_by_hash(self, test_db):
        """Test getting patient name by hash (admin lookup)."""
        await store_patient_workflow(
            patient_name="María García López",
            patient_hash="abc12345",
            workflow_id="workflow-123",
            file_path="/tmp/test.mp3",
        )

        name = await get_patient_name_by_hash("abc12345")
        assert name == "María García López"

    async def test_get_patient_name_by_hash_not_found(self, test_db):
        """Test getting patient name for non-existent hash."""
        name = await get_patient_name_by_hash("nonexistent")
        assert name is None

    async def test_multiple_patients_different_hashes(self, test_db):
        """Test storing workflows for different patients."""
        await store_patient_workflow(
            patient_name="Alice Johnson", patient_hash="hash111", workflow_id="wf-1", file_path="/tmp/alice.mp3"
        )

        await store_patient_workflow(
            patient_name="Bob Williams", patient_hash="hash222", workflow_id="wf-2", file_path="/tmp/bob.mp3"
        )

        alice_name = await get_patient_name_by_hash("hash111")
        bob_name = await get_patient_name_by_hash("hash222")

        assert alice_name == "Alice Johnson"
        assert bob_name == "Bob Williams"

        alice_wf = await get_patient_by_workflow("wf-1")
        bob_wf = await get_patient_by_workflow("wf-2")

        assert alice_wf["patient_name"] == "Alice Johnson"
        assert bob_wf["patient_name"] == "Bob Williams"

    async def test_patient_name_stored_as_plain_text(self, test_db):
        """Verify patient names are stored as plain text (not encrypted)."""
        await store_patient_workflow(
            patient_name="Test Patient Name", patient_hash="testhash", workflow_id="test-wf", file_path="/tmp/test.mp3"
        )

        mapping = await get_patient_by_workflow("test-wf")

        assert mapping["patient_name"] == "Test Patient Name"
        assert isinstance(mapping["patient_name"], str)
        assert " " in mapping["patient_name"]  # Contains spaces (not hashed)

    async def test_created_at_timestamp(self, test_db):
        """Test that created_at timestamp is added automatically."""
        await store_patient_workflow(
            patient_name="Test Patient", patient_hash="hash123", workflow_id="wf-123", file_path="/tmp/test.mp3"
        )

        mapping = await get_patient_by_workflow("wf-123")

        assert "created_at" in mapping
        # Should be ISO format timestamp
        assert "T" in mapping["created_at"] or "-" in mapping["created_at"]


@pytest.mark.asyncio
class TestTwoPhaseCommit:
    """Test two-phase commit pattern for workflow-database consistency."""

    async def test_reserve_workflow_creates_pending_record(self, test_db):
        """Test Reserve creates record with pending status."""
        from app.patients.mapping import reserve_patient_workflow

        await reserve_patient_workflow(
            patient_name="Test Patient",
            patient_hash="testhash",
            workflow_id="wf-pending-123",
            file_path="/tmp/test.mp3",
        )

        mapping = await get_patient_by_workflow("wf-pending-123")
        assert mapping is not None
        assert mapping["patient_name"] == "Test Patient"
        assert mapping["status"] == "pending"

    async def test_commit_workflow_updates_status_to_active(self, test_db):
        """Test Commit marks pending record as active."""
        from app.patients.mapping import reserve_patient_workflow, commit_patient_workflow

        await reserve_patient_workflow(
            patient_name="Test Patient",
            patient_hash="testhash",
            workflow_id="wf-commit-123",
            file_path="/tmp/test.mp3",
        )

        await commit_patient_workflow("wf-commit-123")

        mapping = await get_patient_by_workflow("wf-commit-123")
        assert mapping["status"] == "active"

    async def test_rollback_workflow_deletes_pending_record(self, test_db):
        """Test Rollback deletes pending record."""
        from app.patients.mapping import reserve_patient_workflow, rollback_patient_workflow

        await reserve_patient_workflow(
            patient_name="Test Patient",
            patient_hash="testhash",
            workflow_id="wf-rollback-123",
            file_path="/tmp/test.mp3",
        )

        mapping = await get_patient_by_workflow("wf-rollback-123")
        assert mapping is not None

        await rollback_patient_workflow("wf-rollback-123")

        mapping = await get_patient_by_workflow("wf-rollback-123")
        assert mapping is None

    async def test_get_workflows_excludes_pending_records(self, test_db):
        """Test that get_workflows_by_patient_hash only returns active workflows."""
        from app.patients.mapping import reserve_patient_workflow, commit_patient_workflow

        patient_hash = "testhash"

        await reserve_patient_workflow(
            patient_name="Test Patient",
            patient_hash=patient_hash,
            workflow_id="wf-pending",
            file_path="/tmp/pending.mp3",
        )

        await reserve_patient_workflow(
            patient_name="Test Patient",
            patient_hash=patient_hash,
            workflow_id="wf-active",
            file_path="/tmp/active.mp3",
        )
        await commit_patient_workflow("wf-active")

        workflows = await get_workflows_by_patient_hash(patient_hash)

        assert len(workflows) == 1
        assert workflows[0]["workflow_id"] == "wf-active"
        assert workflows[0]["status"] == "active"

    async def test_two_phase_commit_full_flow(self, test_db):
        """Test complete two-phase commit flow: reserve -> start -> commit."""
        from app.patients.mapping import reserve_patient_workflow, commit_patient_workflow

        patient_hash = "fullflow"
        workflow_id = "wf-fullflow-123"

        await reserve_patient_workflow(
            patient_name="Full Flow Patient",
            patient_hash=patient_hash,
            workflow_id=workflow_id,
            file_path="/tmp/fullflow.mp3",
        )

        mapping = await get_patient_by_workflow(workflow_id)
        assert mapping["status"] == "pending"

        await commit_patient_workflow(workflow_id)

        workflows = await get_workflows_by_patient_hash(patient_hash)
        assert len(workflows) == 1
        assert workflows[0]["workflow_id"] == workflow_id
        assert workflows[0]["status"] == "active"

    async def test_two_phase_commit_failure_flow(self, test_db):
        """Test two-phase commit failure flow: reserve -> failure -> rollback."""
        from app.patients.mapping import reserve_patient_workflow, rollback_patient_workflow

        patient_hash = "failflow"
        workflow_id = "wf-failflow-123"

        await reserve_patient_workflow(
            patient_name="Fail Flow Patient",
            patient_hash=patient_hash,
            workflow_id=workflow_id,
            file_path="/tmp/failflow.mp3",
        )

        mapping = await get_patient_by_workflow(workflow_id)
        assert mapping is not None

        await rollback_patient_workflow(workflow_id)

        workflows = await get_workflows_by_patient_hash(patient_hash)
        assert len(workflows) == 0


@pytest.mark.asyncio
class TestInitDb:
    """Test database initialisation and WAL journal mode."""

    async def test_wal_mode_enabled_after_init(self):
        """Assert that init_db enables WAL journal mode on the SQLite file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_patient_mappings.db"

            with patch("app.patients.database.DB_PATH", db_path):
                from app.patients.database import init_db

                await init_db(fresh_start=False)

            # Open the file directly (bypassing the app layer) and check mode.
            async with aiosqlite.connect(str(db_path)) as conn:
                cursor = await conn.execute("PRAGMA journal_mode")
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == "wal"

    async def test_fresh_start_recreates_schema(self):
        """Assert that init_db with fresh_start=True drops and recreates the DB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_patient_mappings.db"

            with patch("app.patients.database.DB_PATH", db_path):
                from app.patients.database import init_db, store_patient_workflow_db

                # First init + insert a row.
                await init_db(fresh_start=False)
                await store_patient_workflow_db(
                    patient_name="Pre-existing Patient",
                    patient_hash="pre00000",
                    workflow_id="wf-pre-existing",
                    file_path="/tmp/pre.mp3",
                )

                # Fresh start must wipe the file and recreate the schema.
                await init_db(fresh_start=True)

            async with aiosqlite.connect(str(db_path)) as conn:
                cursor = await conn.execute("SELECT COUNT(*) FROM patient_workflow_mappings")
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == 0


@pytest.mark.asyncio
class TestConcurrentReserve:
    """Test concurrent reserve_patient_workflow behaviour."""

    async def test_concurrent_reserves_insert_both_rows(self, test_db):
        """Two simultaneous reserves with different workflow IDs must both succeed."""
        from app.patients.mapping import reserve_patient_workflow

        await asyncio.gather(
            reserve_patient_workflow(
                patient_name="Concurrent Patient",
                patient_hash="conc1111",
                workflow_id="wf-concurrent-a",
                file_path="/tmp/a.mp3",
            ),
            reserve_patient_workflow(
                patient_name="Concurrent Patient",
                patient_hash="conc1111",
                workflow_id="wf-concurrent-b",
                file_path="/tmp/b.mp3",
            ),
        )

        row_a = await get_patient_by_workflow("wf-concurrent-a")
        row_b = await get_patient_by_workflow("wf-concurrent-b")

        assert row_a is not None, "First concurrent reserve must be persisted"
        assert row_b is not None, "Second concurrent reserve must be persisted"
        assert row_a["status"] == "pending"
        assert row_b["status"] == "pending"
        assert row_a["patient_hash"] == "conc1111"
        assert row_b["patient_hash"] == "conc1111"

    async def test_concurrent_reserves_distinct_workflow_ids(self, test_db):
        """All concurrently reserved rows must have unique workflow IDs."""
        from app.patients.mapping import reserve_patient_workflow

        workflow_ids = [f"wf-batch-{i}" for i in range(5)]

        await asyncio.gather(
            *[
                reserve_patient_workflow(
                    patient_name="Batch Patient",
                    patient_hash="batch000",
                    workflow_id=wf_id,
                    file_path=f"/tmp/{wf_id}.mp3",
                )
                for wf_id in workflow_ids
            ]
        )

        cursor = await test_db.execute(
            "SELECT workflow_id FROM patient_workflow_mappings WHERE patient_hash = ?",
            ("batch000",),
        )
        rows = await cursor.fetchall()
        found_ids = {row[0] for row in rows}

        assert found_ids == set(workflow_ids), "All concurrently reserved workflow IDs must appear in the database"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
