"""Unit tests for RateLimitMiddleware."""

import json
import time
from unittest.mock import patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient

from app.middleware.rate_limit_middleware import RateLimitMiddleware, _request_log


# ---------------------------------------------------------------------------
# Shared endpoint and route fixtures
# ---------------------------------------------------------------------------


async def _ok_endpoint(request: Request) -> Response:
    return Response(content=json.dumps({"ok": True}), media_type="application/json")


_ROUTES = [
    Route("/auth/login", _ok_endpoint, methods=["GET", "POST"]),
    Route("/auth/signup", _ok_endpoint, methods=["GET", "POST"]),
    Route("/health", _ok_endpoint),
    Route("/other", _ok_endpoint),
]

_RATE_LIMITED = {"/auth/login"}


def _client(
    max_requests: int,
    window_seconds: int = 60,
    rate_limited_paths: set[str] | None = None,
) -> TestClient:
    """Build a TestClient with RateLimitMiddleware using specified config values."""
    if rate_limited_paths is None:
        rate_limited_paths = _RATE_LIMITED

    app = Starlette(routes=_ROUTES)
    app.add_middleware(RateLimitMiddleware)

    with (
        patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_REQUESTS", max_requests),
        patch(
            "app.middleware.rate_limit_middleware.Config.RATE_LIMIT_WINDOW_SECONDS",
            window_seconds,
        ),
        patch(
            "app.middleware.rate_limit_middleware.Config.RATE_LIMITED_PATHS",
            rate_limited_paths,
        ),
    ):
        # Entering the TestClient context triggers ASGI startup, which instantiates
        # the middleware via its __init__ — Config patches must be active here.
        tc = TestClient(app, raise_server_exceptions=True)
        # Force initialisation by performing a dummy request
        tc.get("/health")

    return tc


@pytest.fixture(autouse=True)
def clear_request_log() -> None:
    """Clear the per-IP request log before each test to avoid cross-test pollution."""
    _request_log.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    """RateLimitMiddleware behaviour."""

    def test_requests_within_limit_pass(self) -> None:
        """All requests within the window limit receive a 200 response."""
        app = Starlette(routes=_ROUTES)
        app.add_middleware(RateLimitMiddleware)
        with (
            patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_REQUESTS", 3),
            patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_WINDOW_SECONDS", 60),
            patch(
                "app.middleware.rate_limit_middleware.Config.RATE_LIMITED_PATHS",
                {"/auth/login"},
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            # Drain any counter from the health check done in _client(); start fresh
            _request_log.clear()
            for _ in range(3):
                resp = client.post("/auth/login")
                assert resp.status_code == 200

    def test_request_exceeding_limit_returns_429(self) -> None:
        """The (max_requests + 1)th request returns HTTP 429."""
        app = Starlette(routes=_ROUTES)
        app.add_middleware(RateLimitMiddleware)
        with (
            patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_REQUESTS", 3),
            patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_WINDOW_SECONDS", 60),
            patch(
                "app.middleware.rate_limit_middleware.Config.RATE_LIMITED_PATHS",
                {"/auth/login"},
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            _request_log.clear()
            for _ in range(3):
                client.post("/auth/login")
            resp = client.post("/auth/login")
        assert resp.status_code == 429

    def test_429_includes_retry_after_header(self) -> None:
        """HTTP 429 response includes a Retry-After header with a positive integer."""
        app = Starlette(routes=_ROUTES)
        app.add_middleware(RateLimitMiddleware)
        with (
            patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_REQUESTS", 2),
            patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_WINDOW_SECONDS", 60),
            patch(
                "app.middleware.rate_limit_middleware.Config.RATE_LIMITED_PATHS",
                {"/auth/login"},
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            _request_log.clear()
            client.post("/auth/login")
            client.post("/auth/login")
            resp = client.post("/auth/login")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers
        assert int(resp.headers["retry-after"]) > 0

    def test_non_rate_limited_path_passes_freely(self) -> None:
        """Paths not in RATE_LIMITED_PATHS are never throttled."""
        app = Starlette(routes=_ROUTES)
        app.add_middleware(RateLimitMiddleware)
        with (
            patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_REQUESTS", 2),
            patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_WINDOW_SECONDS", 60),
            patch(
                "app.middleware.rate_limit_middleware.Config.RATE_LIMITED_PATHS",
                {"/auth/login"},
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            _request_log.clear()
            for _ in range(10):
                resp = client.get("/health")
                assert resp.status_code == 200

    def test_different_ips_are_independent(self) -> None:
        """Rate limits are tracked per IP; one IP's limit does not affect another."""
        app = Starlette(routes=_ROUTES)
        app.add_middleware(RateLimitMiddleware)
        with (
            patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_REQUESTS", 2),
            patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_WINDOW_SECONDS", 60),
            patch(
                "app.middleware.rate_limit_middleware.Config.RATE_LIMITED_PATHS",
                {"/auth/login"},
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            _request_log.clear()
            # Exhaust limit for the default TestClient IP
            client.post("/auth/login")
            client.post("/auth/login")
            assert client.post("/auth/login").status_code == 429
            # A different IP via X-Forwarded-For should still be allowed
            resp = client.post("/auth/login", headers={"X-Forwarded-For": "10.0.0.1"})
        assert resp.status_code == 200

    def test_window_expiry_allows_new_requests(self) -> None:
        """Requests older than the window are pruned; new requests are allowed."""
        app = Starlette(routes=_ROUTES)
        app.add_middleware(RateLimitMiddleware)
        with (
            patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_REQUESTS", 2),
            patch("app.middleware.rate_limit_middleware.Config.RATE_LIMIT_WINDOW_SECONDS", 60),
            patch(
                "app.middleware.rate_limit_middleware.Config.RATE_LIMITED_PATHS",
                {"/auth/login"},
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            _request_log.clear()
            # Exhaust the limit
            client.post("/auth/login")
            client.post("/auth/login")
            assert client.post("/auth/login").status_code == 429

            # Manually expire all timestamps in the request log for this IP
            if _request_log:
                ip_key = list(_request_log.keys())[0]
                timestamps = _request_log[ip_key]
                # Replace with a timestamp well outside the 60-second window
                timestamps.clear()
                timestamps.append(time.monotonic() - 120)

            # After expiry, request should pass again
            resp = client.post("/auth/login")
        assert resp.status_code == 200
