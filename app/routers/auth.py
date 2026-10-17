"""Auth API — POST /auth/login for the mobile-app mock accounts."""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from jose import jwt
from pydantic import BaseModel

from ..config import Config
from ..logger import logger
from ..services.user_store import get_user_by_email, hash_password, verify_password

router = APIRouter(tags=["Auth"])

# Module-local so Config.validate_medical_config still sees a missing key.
JWT_SECRET = Config.JWT_SECRET_KEY or secrets.token_hex(32)
if not Config.JWT_SECRET_KEY:
    # Dev convenience: tokens stay valid for this process only.
    logger.warning("JWT_SECRET_KEY not set; generated an ephemeral secret (tokens die with this process)")

# Checked against on unknown emails so both 401 paths pay the same bcrypt cost.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


class LoginRequest(BaseModel):
    # Plain str, not EmailStr: email-validator is not a dependency of this service.
    email: str
    password: str


class UserPublic(BaseModel):
    id: int
    email: str
    full_name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserPublic


class AuthError(HTTPException):
    """HTTPException carrying ``error_code``; flattened by the handler in app.main."""

    def __init__(self, status_code: int, detail: str, error_code: str):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


@router.post("/auth/login", summary="Log in with email + password (mock accounts)")
async def login(body: LoginRequest) -> LoginResponse:
    user = get_user_by_email(body.email)
    password_ok = verify_password(body.password, user["password_hash"] if user else _DUMMY_HASH)
    if not user or not password_ok:
        # Same response and timing for unknown email and wrong password: no user enumeration.
        raise AuthError(401, "Invalid email or password", "invalid_credentials")

    expires = datetime.now(timezone.utc) + timedelta(minutes=Config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    token = jwt.encode(
        {"sub": str(user["id"]), "exp": expires},
        JWT_SECRET,
        algorithm=Config.JWT_ALGORITHM,
    )
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserPublic(id=user["id"], email=user["email"], full_name=user["full_name"], role=user["role"]),
    )
