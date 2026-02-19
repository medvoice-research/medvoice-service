"""Unit tests for AuthMiddleware."""

import json
from typing import Any
from unittest.mock import patch

from starlette.requests import Request
from starlette.responses import Response
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route

from app.middleware.auth_middleware import AuthMiddleware, _DEV_USER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(auth_enabled: bool = True) -> Starlette:
    """Build a minimal Starlette app with AuthMiddleware for testing.

    Args:
        auth_enabled: Whether to enable authentication in Config.

    Returns:
        Starlette test application.
    """

    async def protected_endpoint(request: Request) -> Response:
        user = getattr(request.state, "current_user", None)
        return Response(
            content=json.dumps({"user": user}),
            media_type="application/json",
        )

    async def public_endpoint(request: Request) -> Response:
        return Response(content=json.dumps({"status": "ok"}), media_type="application/json")

    routes = [
        Route("/protected", protected_endpoint),
        Route("/health", public_endpoint),
        Route("/health/live", public_endpoint),
        Route("/", public_endpoint),
        Route("/docs", public_endpoint),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(AuthMiddleware)
    return app


def _valid_payload() -> dict[str, Any]:
    return {
        "user_id": "u1",
        "username": "test@example.com",
        "role": "physician",
        "full_name": "Test User",
    }


# ---------------------------------------------------------------------------
# Tests: authentication disabled (dev mode)
# ---------------------------------------------------------------------------


class TestAuthMiddlewareDisabled:
    """AuthMiddleware behaviour when ENABLE_AUTHENTICATION is False."""

    def test_injects_dev_user_on_any_path(self) -> None:
        """All requests receive the synthetic dev user without a token."""
        with patch("app.middleware.auth_middleware.Config") as mock_cfg:
            mock_cfg.ENABLE_AUTHENTICATION = False
            mock_cfg.PUBLIC_PATHS = {"/health", "/"}
            app = _make_app(auth_enabled=False)
            client = TestClient(app, raise_server_exceptions=True)
            # Patch Config inside the already-instantiated middleware
            with patch("app.middleware.auth_middleware.Config.ENABLE_AUTHENTICATION", False):
                resp = client.get("/protected")
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"] == _DEV_USER

    def test_public_path_no_token_passes(self) -> None:
        """Public paths pass through with no auth header even when auth is enabled."""
        with patch("app.middleware.auth_middleware.Config.ENABLE_AUTHENTICATION", False):
            client = TestClient(_make_app())
            resp = client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tests: authentication enabled
# ---------------------------------------------------------------------------


class TestAuthMiddlewareEnabled:
    """AuthMiddleware behaviour when ENABLE_AUTHENTICATION is True."""

    def _client(self) -> TestClient:
        app = _make_app()
        return TestClient(app, raise_server_exceptions=False)

    def test_missing_token_returns_401(self) -> None:
        """Request with no Authorization header on protected path returns 401."""
        with (
            patch("app.middleware.auth_middleware.Config.ENABLE_AUTHENTICATION", True),
            patch(
                "app.middleware.auth_middleware.Config.PUBLIC_PATHS",
                {"/health", "/health/live", "/", "/docs"},
            ),
        ):
            client = self._client()
            resp = client.get("/protected")
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"] == "Bearer"

    def test_malformed_token_returns_401(self) -> None:
        """Request with malformed token returns 401."""
        with (
            patch("app.middleware.auth_middleware.Config.ENABLE_AUTHENTICATION", True),
            patch(
                "app.middleware.auth_middleware.Config.PUBLIC_PATHS",
                {"/health", "/health/live", "/", "/docs"},
            ),
            patch(
                "app.middleware.auth_middleware._access_control.verify_token",
                side_effect=Exception("invalid token"),
            ),
        ):
            client = self._client()
            resp = client.get("/protected", headers={"Authorization": "Bearer bad.token.here"})
        assert resp.status_code == 401

    def test_valid_token_sets_state_and_returns_200(self) -> None:
        """Valid JWT populates request.state.current_user and passes the request."""
        payload = _valid_payload()
        with (
            patch("app.middleware.auth_middleware.Config.ENABLE_AUTHENTICATION", True),
            patch(
                "app.middleware.auth_middleware.Config.PUBLIC_PATHS",
                {"/health", "/health/live", "/", "/docs"},
            ),
            patch(
                "app.middleware.auth_middleware._access_control.verify_token",
                return_value=payload,
            ),
        ):
            client = self._client()
            resp = client.get("/protected", headers={"Authorization": "Bearer valid.token.here"})
        assert resp.status_code == 200
        assert resp.json()["user"] == payload

    def test_public_path_passes_without_token(self) -> None:
        """Public paths bypass auth enforcement entirely."""
        with (
            patch("app.middleware.auth_middleware.Config.ENABLE_AUTHENTICATION", True),
            patch(
                "app.middleware.auth_middleware.Config.PUBLIC_PATHS",
                {"/health", "/health/live", "/", "/docs"},
            ),
        ):
            client = self._client()
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_non_bearer_scheme_returns_401(self) -> None:
        """Authorization header with wrong scheme returns 401."""
        with (
            patch("app.middleware.auth_middleware.Config.ENABLE_AUTHENTICATION", True),
            patch(
                "app.middleware.auth_middleware.Config.PUBLIC_PATHS",
                {"/health", "/health/live", "/", "/docs"},
            ),
        ):
            client = self._client()
            resp = client.get("/protected", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert resp.status_code == 401
