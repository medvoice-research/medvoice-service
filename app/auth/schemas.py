"""Pydantic request/response schemas for authentication."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class SignUpRequest(BaseModel):
    """Request body for user registration."""

    email: EmailStr
    password: str
    full_name: str
    role: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        """Enforce minimum password length."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str) -> str:
        """Validate role against allowed values."""
        allowed = {"physician", "nurse", "administrator"}
        if v.lower() not in allowed:
            raise ValueError(f"Role must be one of: {', '.join(sorted(allowed))}")
        return v.lower()


class LoginRequest(BaseModel):
    """Request body for user login."""

    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    """Response body for successful authentication."""

    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    """Public user representation (no password)."""

    id: int
    email: str
    full_name: str
    role: str
    created_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}
