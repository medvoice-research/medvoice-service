"""Unit tests for authentication endpoints and get_current_user dependency."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def _make_app():
    """Import and return the FastAPI app with auth DB mocked out."""
    with (
        patch("app.auth.models.init_auth_db", new_callable=AsyncMock),
        patch("app.patients.database.init_db"),
        patch("app.temporal.manager.temporal_manager.get_client", new_callable=AsyncMock),
    ):
        from app.main import app

        return app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Sync TestClient with auth disabled and an in-memory-like DB override."""
    monkeypatch.setenv("ENABLE_AUTHENTICATION", "false")
    monkeypatch.setenv("AUTH_SECRET", "test-secret-key-for-testing-only")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-testing-only")

    # Override the raw POSTGRES_URL used by init_auth_db
    monkeypatch.setenv("POSTGRES_URL", f"sqlite+aiosqlite:///{tmp_path}/test_auth.db")

    app = _make_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


class TestSignup:
    """Tests for POST /auth/signup."""

    def _valid_payload(self, email: str = "doctor@hospital.example.com") -> dict:
        return {
            "email": email,
            "password": "SecurePass1",
            "full_name": "Dr. Test",
            "role": "physician",
        }

    def test_signup_success(self, client):
        with (
            patch("app.routers.auth.create_user") as mock_create,
            patch("app.routers.auth._access_control.hash_password", return_value="$2b$12$fakehash"),
        ):
            from datetime import datetime

            fake_user = MagicMock()
            fake_user.id = 1
            fake_user.email = "doctor@hospital.example.com"
            fake_user.full_name = "Dr. Test"
            fake_user.role = "physician"
            fake_user.created_at = datetime(2024, 1, 1)
            fake_user.is_active = True

            mock_create.return_value = fake_user

            with patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=None):
                mock_create_async = AsyncMock(return_value=fake_user)
                with patch("app.routers.auth.create_user", mock_create_async):
                    response = client.post("/auth/signup", json=self._valid_payload())

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "doctor@hospital.example.com"

    def test_signup_duplicate_email(self, client):
        from datetime import datetime

        fake_user = MagicMock()
        fake_user.id = 1
        fake_user.email = "doctor@hospital.example.com"
        fake_user.full_name = "Dr. Test"
        fake_user.role = "physician"
        fake_user.created_at = datetime(2024, 1, 1)
        fake_user.is_active = True

        with patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=fake_user):
            response = client.post("/auth/signup", json=self._valid_payload())

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_signup_weak_password(self, client):
        payload = self._valid_payload()
        payload["password"] = "short"
        response = client.post("/auth/signup", json=payload)
        assert response.status_code == 422

    def test_signup_invalid_role(self, client):
        payload = self._valid_payload()
        payload["role"] = "hacker"
        response = client.post("/auth/signup", json=payload)
        assert response.status_code == 422

    def test_signup_race_condition(self, client):
        """Simulate concurrent insert where create_user returns None (IntegrityError)."""
        with (
            patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=None),
            patch("app.routers.auth.create_user", new_callable=AsyncMock, return_value=None),
            patch("app.routers.auth._access_control.hash_password", return_value="$2b$12$fakehash"),
        ):
            response = client.post("/auth/signup", json=self._valid_payload())

        assert response.status_code == 409


class TestLogin:
    """Tests for POST /auth/login."""

    def _valid_payload(self) -> dict:
        return {"email": "doctor@hospital.example.com", "password": "SecurePass1"}

    def _fake_user(self, hashed_password: str = "$2b$12$fakehash"):
        from datetime import datetime

        user = MagicMock()
        user.id = 1
        user.email = "doctor@hospital.example.com"
        user.hashed_password = hashed_password
        user.full_name = "Dr. Test"
        user.role = "physician"
        user.created_at = datetime(2024, 1, 1)
        user.is_active = True
        return user

    def test_login_success(self, client):
        fake_user = self._fake_user()

        with (
            patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=fake_user),
            patch("app.routers.auth._access_control.verify_password", return_value=True),
        ):
            response = client.post("/auth/login", json=self._valid_payload())

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "physician"

    def test_login_wrong_password(self, client):
        fake_user = self._fake_user()

        with (
            patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=fake_user),
            patch("app.routers.auth._access_control.verify_password", return_value=False),
        ):
            response = client.post("/auth/login", json=self._valid_payload())

        assert response.status_code == 401

    def test_login_unknown_email(self, client):
        with patch("app.routers.auth.get_user_by_email", new_callable=AsyncMock, return_value=None):
            response = client.post("/auth/login", json=self._valid_payload())

        assert response.status_code == 401


class TestGetCurrentUser:
    """Tests for app.auth.dependencies.get_current_user."""

    @pytest.mark.asyncio
    async def test_auth_disabled_returns_dev_user(self, monkeypatch):
        monkeypatch.setenv("ENABLE_AUTHENTICATION", "false")
        monkeypatch.setenv("AUTH_SECRET", "test-secret-key-for-testing-only")
        from app.auth.dependencies import get_current_user

        result = await get_current_user(credentials=None)
        assert result["user_id"] == "dev_user"

    @pytest.mark.asyncio
    async def test_valid_token_returns_payload(self, monkeypatch):
        monkeypatch.setenv("ENABLE_AUTHENTICATION", "true")
        monkeypatch.setenv("AUTH_SECRET", "test-secret-key-for-testing-only")

        from fastapi.security import HTTPAuthorizationCredentials

        fake_payload = {"user_id": "42", "role": "physician"}

        with patch("app.auth.dependencies._access_control.verify_token", return_value=fake_payload):
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="fake.jwt.token")
            from app.auth.dependencies import get_current_user

            result = await get_current_user(credentials=creds)

        assert result["user_id"] == "42"

    @pytest.mark.asyncio
    async def test_missing_token_raises_401(self, monkeypatch):
        monkeypatch.setenv("ENABLE_AUTHENTICATION", "true")
        from app.auth.dependencies import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self, monkeypatch):
        monkeypatch.setenv("ENABLE_AUTHENTICATION", "true")

        from fastapi import HTTPException as FastAPIHTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        with patch(
            "app.auth.dependencies._access_control.verify_token",
            side_effect=FastAPIHTTPException(status_code=401, detail="Token expired"),
        ):
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="expired.jwt.token")
            from app.auth.dependencies import get_current_user

            with pytest.raises(FastAPIHTTPException) as exc_info:
                await get_current_user(credentials=creds)

            assert exc_info.value.status_code == 401
