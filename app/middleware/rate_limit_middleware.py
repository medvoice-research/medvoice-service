"""Per-IP sliding-window rate limiting middleware for sensitive endpoints."""

import json
import logging
import time
from collections import deque
from typing import Any, Deque, Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..config import Config

logger = logging.getLogger(__name__)

# Module-level store: IP address -> deque of request timestamps (floats)
_request_log: Dict[str, Deque[float]] = {}


def _get_client_ip(request: Request) -> str:
    """Extract the client IP from the request, respecting X-Forwarded-For."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _json_429(retry_after: int) -> Response:
    """Build a plain HTTP 429 JSON response."""
    body = json.dumps({"detail": "Too many requests"})
    return Response(
        content=body,
        status_code=429,
        headers={
            "Retry-After": str(retry_after),
            "Content-Type": "application/json",
        },
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces per-IP sliding-window rate limits.

    Only paths in ``Config.RATE_LIMITED_PATHS`` are subject to rate limiting.
    All other paths pass through without any counter increment.

    The rate limit window and threshold are read from ``Config`` at construction
    time so they can be overridden in tests via monkeypatching."""

    def __init__(self, app: Any) -> None:
        """Initialise the middleware, reading config from Config class."""
        super().__init__(app)
        self._max_requests: int = Config.RATE_LIMIT_REQUESTS
        self._window_seconds: int = Config.RATE_LIMIT_WINDOW_SECONDS
        self._rate_limited_paths: set[str] = Config.RATE_LIMITED_PATHS

    def _is_rate_limited_path(self, path: str) -> bool:
        """Check if the given path should be rate-limited."""
        return any(path.startswith(p) for p in self._rate_limited_paths)

    def _check_rate_limit(self, ip: str) -> int:
        """Apply the sliding-window algorithm for the given IP.

        Prunes timestamps older than the window, then counts remaining
        requests. Returns 0 if within the limit; returns the seconds until
        the oldest request expires if the limit is exceeded."""
        now = time.monotonic()
        window_start = now - self._window_seconds

        if ip not in _request_log:
            _request_log[ip] = deque()

        timestamps = _request_log[ip]

        # Evict timestamps outside the current window
        while timestamps and timestamps[0] <= window_start:
            timestamps.popleft()

        if len(timestamps) >= self._max_requests:
            # How long until the oldest timestamp leaves the window
            retry_after = int(timestamps[0] - window_start) + 1
            return retry_after

        timestamps.append(now)
        return 0

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process the request through the rate-limit check."""
        path = request.url.path
        if not self._is_rate_limited_path(path):
            return await call_next(request)

        ip = _get_client_ip(request)
        retry_after = self._check_rate_limit(ip)
        if retry_after > 0:
            logger.warning("Rate limit exceeded for IP %s on path %s", ip, path)
            return _json_429(retry_after)

        return await call_next(request)
