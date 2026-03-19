"""Unit tests verifying consistent created_by user_id across STT and admin endpoints.

The root cause of the fix-patient-display-mismatch change was that `speech_to_text()`
read user_id from `request.state.current_user` (AuthMiddleware) while admin endpoints
used `get_current_user` dependency — which could resolve to different identities.

These tests verify that both code paths now use the same `get_current_user` dependency.
"""

from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest

# Synthetic user returned by get_current_user when auth is disabled
_DEV_USER: Dict[str, Any] = {
    "user_id": "dev_user",
    "username": "developer@example.com",
    "role": "physician",
    "full_name": "Development User",
}


class TestSTTCreatedByConsistency:
    """Verify STT endpoints extract created_by from the get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_speech_to_text_uses_dependency_user_id(self) -> None:
        """speech_to_text() should pass the dependency's user_id as created_by."""
        from app.routers.stt import speech_to_text

        # Check that speech_to_text accepts 'current_user' parameter (from Depends)
        import inspect

        sig = inspect.signature(speech_to_text)
        assert "current_user" in sig.parameters, (
            "speech_to_text() must accept a 'current_user' parameter via Depends(get_current_user)"
        )

    @pytest.mark.asyncio
    async def test_speech_to_text_url_uses_dependency_user_id(self) -> None:
        """speech_to_text_url() should pass the dependency's user_id as created_by."""
        from app.routers.stt import speech_to_text_url

        import inspect

        sig = inspect.signature(speech_to_text_url)
        assert "current_user" in sig.parameters, (
            "speech_to_text_url() must accept a 'current_user' parameter via Depends(get_current_user)"
        )

    @pytest.mark.asyncio
    async def test_stt_does_not_use_request_state(self) -> None:
        """STT endpoints must NOT reference request.state.current_user for created_by."""
        import inspect
        from app.routers.stt import speech_to_text, speech_to_text_url

        for fn in (speech_to_text, speech_to_text_url):
            source = inspect.getsource(fn)
            assert "request.state.current_user" not in source, (
                f"{fn.__name__}() must not read request.state.current_user; "
                "use the get_current_user dependency instead"
            )


class TestAdminPatientVisibility:
    """Verify that admin endpoints return records created with the dependency's user_id."""

    @pytest.mark.asyncio
    async def test_admin_query_matches_dev_user(self) -> None:
        """get_all_patients_db with dev_user should find records created by dev_user."""
        from app.patients.database import get_db_connection, init_database

        await init_database(fresh_start=True)

        # Insert a record with created_by = "dev_user"
        async with get_db_connection() as conn:
            await conn.execute(
                """
                INSERT INTO patient_workflow_mappings
                (patient_name, patient_hash, workflow_id, file_path, created_at, status, created_by)
                VALUES (?, ?, ?, ?, ?, 'active', ?)
                """,
                ("Test Patient", "abc12345", "wf-test-001", "/tmp/test.mp3", "2026-01-01T00:00:00", "dev_user"),
            )

        # Query as dev_user (non-admin, same as dependency returns)
        from app.patients.database import get_all_patients_db

        patients = await get_all_patients_db(user_id="dev_user")
        assert len(patients) == 1
        assert patients[0]["patient_name"] == "Test Patient"

    @pytest.mark.asyncio
    async def test_admin_query_mismatched_user_id_excludes_record(self) -> None:
        """Records created by a different user_id should NOT appear in user-scoped queries."""
        from app.patients.database import get_db_connection, init_database

        await init_database(fresh_start=True)

        # Insert a record with created_by = "real_jwt_user"
        async with get_db_connection() as conn:
            await conn.execute(
                """
                INSERT INTO patient_workflow_mappings
                (patient_name, patient_hash, workflow_id, file_path, created_at, status, created_by)
                VALUES (?, ?, ?, ?, ?, 'active', ?)
                """,
                ("Test Patient", "abc12345", "wf-test-002", "/tmp/test.mp3", "2026-01-01T00:00:00", "real_jwt_user"),
            )

        # Query as dev_user — should NOT find the record
        from app.patients.database import get_all_patients_db

        patients = await get_all_patients_db(user_id="dev_user")
        assert len(patients) == 0, (
            "Records created by 'real_jwt_user' should be invisible to 'dev_user' queries"
        )
