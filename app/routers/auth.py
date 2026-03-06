"""Authentication router: signup and login endpoints."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status

from ..auth.repository import create_user, get_user_by_email
from ..auth.schemas import AuthResponse, LoginRequest, SignUpRequest, UserOut
from ..hipaa.access_control import HIPAAAccessControl
from ..hipaa.audit_logger import HIPAAAuditLogger

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])

_access_control = HIPAAAccessControl()
# 8-hour token expiry — one clinical shift
_access_control.access_token_expire_minutes = 8 * 60
_audit_logger = HIPAAAuditLogger()


def _client_ip(request: Request) -> str:
    """Extract client IP address from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@auth_router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new medical staff account",
)
async def signup(body: SignUpRequest, request: Request) -> AuthResponse:
    """Register a new user and return a signed JWT.

    Args:
        body: SignUpRequest with email, password, full_name, and role.
        request: FastAPI Request (used for audit logging).

    Returns:
        AuthResponse containing the access token and user details.

    Raises:
        HTTPException 409: If the email is already registered.
    """
    existing = await get_user_by_email(body.email)
    if existing is not None:
        _audit_logger.log_authentication_event(
            user_id=body.email,
            event_type="failed_login",
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent") or "",
            success=False,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    hashed = _access_control.hash_password(body.password)
    user = await create_user(
        email=body.email,
        hashed_password=hashed,
        full_name=body.full_name,
        role=body.role,
    )

    if user is None:
        # Race condition: another request inserted the same email between our check and insert
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    token_payload: Dict[str, Any] = {
        "user_id": str(user.id),
        "username": user.email,
        "role": user.role,
        "full_name": user.full_name,
    }
    token = _access_control.create_access_token(token_payload)

    _audit_logger.log_authentication_event(
        user_id=str(user.id),
        event_type="login",
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent") or "",
        success=True,
    )

    return AuthResponse(
        access_token=token,
        user=UserOut.model_validate(user),
    )


@auth_router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and obtain a JWT",
)
async def login(body: LoginRequest, request: Request) -> AuthResponse:
    """Validate credentials and return a signed JWT.

    Args:
        body: LoginRequest with email and password.
        request: FastAPI Request (used for audit logging).

    Returns:
        AuthResponse containing the access token and user details.

    Raises:
        HTTPException 401: If the email is not found or the password is incorrect.
    """
    user = await get_user_by_email(body.email)

    if user is None or not _access_control.verify_password(body.password, str(user.hashed_password)):
        _audit_logger.log_authentication_event(
            user_id=body.email,
            event_type="failed_login",
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent") or "",
            success=False,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not bool(user.is_active):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
        )

    token_payload: Dict[str, Any] = {
        "user_id": str(user.id),
        "username": user.email,
        "role": user.role,
        "full_name": user.full_name,
    }
    token = _access_control.create_access_token(token_payload)

    _audit_logger.log_authentication_event(
        user_id=str(user.id),
        event_type="login",
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent") or "",
        success=True,
    )

    return AuthResponse(
        access_token=token,
        user=UserOut.model_validate(user),
    )
