"""HTTP authentication middleware for centralized JWT enforcement."""

import json
import logging
from typing import Any, Dict

from fastapi import Request
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..config import Config
from ..hipaa.access_control import HIPAAAccessControl

logger = logging.getLogger(__name__)

_access_control = HIPAAAccessControl()

# Dev-mode synthetic user returned when ENABLE_AUTHENTICATION is False
_DEV_USER: Dict[str, Any] = {
    "user_id": "dev_user",
    "username": "developer@example.com",
    "role": "physician",
    "full_name": "Development User",
}


def _is_public_path(path: str) -> bool:
    """Return True if path matches any entry in the PUBLIC_PATHS allowlist.

    Matching rules:
    - Entries ending with ``/`` are treated as prefix matchers (e.g. ``/auth/``
      matches ``/auth/login``).
    - All other entries are exact matches (e.g. ``/health`` matches ``/health``
      but also ``/health/live`` because ``/health`` is a path segment prefix).
    - The bare ``/`` entry matches only the root path to avoid matching every
      request.
    """
    for prefix in Config.PUBLIC_PATHS:
        if prefix == "/":
            if path == "/":
                return True
        elif prefix.endswith("/"):
            # Prefix match: /auth/ matches /auth/login, /auth/signup
            if path.startswith(prefix) or path == prefix.rstrip("/"):
                return True
        else:
            # Segment match: /health matches /health and /health/live
            if path == prefix or path.startswith(prefix + "/"):
                return True
    return False


def _json_401(detail: str) -> Response:
    """Build a plain HTTP 401 JSON response without going through FastAPI."""
    body = json.dumps({"detail": detail})
    return Response(
        content=body,
        status_code=401,
        headers={
            "WWW-Authenticate": "Bearer",
            "Content-Type": "application/json",
        },
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces JWT Bearer authentication.

    Validates the Authorization header on every request that is not on the
    public-path allowlist. On success, stores the decoded payload in
    ``request.state.current_user`` so downstream dependencies and handlers
    can access it without re-decoding the token.

    When ``Config.ENABLE_AUTHENTICATION`` is False the middleware injects the
    synthetic dev-user dict and forwards every request unconditionally.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request through auth validation."""
        if not Config.ENABLE_AUTHENTICATION:
            request.state.current_user = _DEV_USER
            return await call_next(request)

        path = request.url.path
        if _is_public_path(path):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _json_401("Not authenticated")

        token = auth_header[len("Bearer ") :]
        try:
            payload = _access_control.verify_token(token)
        except (JWTError, Exception) as exc:
            logger.debug("Token validation failed: %s", exc)
            return _json_401("Invalid or expired token")

        request.state.current_user = payload
        return await call_next(request)
