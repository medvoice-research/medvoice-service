"""FastAPI dependency for extracting and validating the current user from JWT."""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..hipaa.access_control import HIPAAAccessControl

logger = logging.getLogger(__name__)

_access_control = HIPAAAccessControl()
_bearer_scheme = HTTPBearer(auto_error=False)

# Override token expiry to 8 hours (one clinical shift)
_access_control.access_token_expire_minutes = 8 * 60


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Dict[str, Any]:
    """Extract and validate Bearer JWT; return the decoded payload.

    Reads ENABLE_AUTHENTICATION directly from the environment so that the
    Config.ENABLE_AUTHENTICATION hardcoded False is bypassed at runtime."""
    enable_auth = os.environ.get("ENABLE_AUTHENTICATION", "false").lower() == "true"

    if not enable_auth:
        # Development bypass: return a synthetic admin context
        return {
            "user_id": "dev_user",
            "username": "developer@example.com",
            "role": "physician",
            "full_name": "Development User",
        }

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _access_control.verify_token(credentials.credentials)
