"""HIPAA-compliant access control with role-based permissions."""

import os
import logging
from enum import Enum
from typing import Dict, List, Any
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt

logger = logging.getLogger(__name__)


class HealthcareRole(str, Enum):
    """Healthcare provider roles with different access levels."""

    PHYSICIAN = "physician"
    NURSE = "nurse"
    RESIDENT = "resident"
    MEDICAL_ASSISTANT = "medical_assistant"
    ADMINISTRATOR = "administrator"
    RESEARCHER = "researcher"
    AUDITOR = "auditor"
    IT_ADMIN = "it_admin"


class Permission(str, Enum):
    """Individual permissions for PHI access."""

    READ_PHI = "read_phi"  # Read PHI for treatment
    WRITE_PHI = "write_phi"  # Create/modify PHI
    DELETE_PHI = "delete_phi"  # Delete PHI (rare, audit required)
    REVEAL_PHI = "reveal_phi"  # Remove anonymization for treatment
    EXPORT_PHI = "export_phi"  # Export PHI from system
    SEARCH_PHI = "search_phi"  # Search across patient records
    VIEW_AUDIT_LOG = "view_audit_log"  # Access audit logs
    MANAGE_USERS = "manage_users"  # User account management
    SYSTEM_CONFIG = "system_config"  # System configuration
    RESEARCH_ACCESS = "research_access"  # Access anonymized data for research
    QUALITY_REVIEW = "quality_review"  # Quality assurance and review
    EMERGENCY_ACCESS = "emergency_access"  # Break-glass emergency access


# Role-based permission matrix
ROLE_PERMISSIONS = {
    HealthcareRole.PHYSICIAN: [
        Permission.READ_PHI,
        Permission.WRITE_PHI,
        Permission.REVEAL_PHI,
        Permission.EXPORT_PHI,
        Permission.SEARCH_PHI,
        Permission.QUALITY_REVIEW,
        Permission.EMERGENCY_ACCESS,
    ],
    HealthcareRole.NURSE: [
        Permission.READ_PHI,
        Permission.WRITE_PHI,
        Permission.REVEAL_PHI,
        Permission.SEARCH_PHI,
        Permission.EMERGENCY_ACCESS,
    ],
    HealthcareRole.RESIDENT: [
        Permission.READ_PHI,
        Permission.WRITE_PHI,
        Permission.REVEAL_PHI,
        Permission.SEARCH_PHI,
        Permission.QUALITY_REVIEW,
        Permission.EMERGENCY_ACCESS,
    ],
    HealthcareRole.MEDICAL_ASSISTANT: [
        Permission.READ_PHI,
        Permission.WRITE_PHI,
        Permission.SEARCH_PHI,
    ],
    HealthcareRole.ADMINISTRATOR: [
        Permission.READ_PHI,
        Permission.EXPORT_PHI,
        Permission.SEARCH_PHI,
        Permission.VIEW_AUDIT_LOG,
        Permission.QUALITY_REVIEW,
    ],
    HealthcareRole.RESEARCHER: [
        Permission.RESEARCH_ACCESS,
        Permission.SEARCH_PHI,  # Limited to anonymized data
    ],
    HealthcareRole.AUDITOR: [
        Permission.VIEW_AUDIT_LOG,
        Permission.READ_PHI,
        Permission.SEARCH_PHI,
        Permission.EXPORT_PHI,
    ],
    HealthcareRole.IT_ADMIN: [
        Permission.SYSTEM_CONFIG,
        Permission.MANAGE_USERS,
        Permission.VIEW_AUDIT_LOG,
        Permission.READ_PHI,  # For system maintenance only
    ],
}

# Context-specific permission requirements
CONTEXT_PERMISSIONS = {
    "patient_treatment": [Permission.READ_PHI, Permission.WRITE_PHI],
    "emergency_care": [Permission.EMERGENCY_ACCESS],
    "quality_assurance": [Permission.QUALITY_REVIEW],
    "research": [Permission.RESEARCH_ACCESS],
    "auditing": [Permission.VIEW_AUDIT_LOG],
    "system_admin": [Permission.SYSTEM_CONFIG],
    "user_management": [Permission.MANAGE_USERS],
}


class HIPAAAccessControl:
    """Role-based access control system for HIPAA compliance."""

    def __init__(self):
        self.oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

        # Load JWT configuration
        self.secret_key = os.environ.get("AUTH_SECRET")
        if not self.secret_key:
            logger.error("AUTH_SECRET not set in environment. JWT verification will fail.")
            raise ValueError("AUTH_SECRET environment variable is strictly required for operation.")

        self.algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
        self.access_token_expire_minutes = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    def create_access_token(self, user_data: Dict[str, Any]) -> str:
        """Create JWT access token for user."""
        to_encode = user_data.copy()

        # Add expiration time
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access_token"})

        # Create JWT token
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError as e:
            logger.warning(f"JWT token verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def check_permission(self, user_role: HealthcareRole, permission: Permission) -> bool:
        role_permissions = ROLE_PERMISSIONS.get(user_role, [])
        return permission in role_permissions

    def check_context_permissions(
        self, user_role: HealthcareRole, context: str, additional_permissions: List[Permission] = None
    ) -> bool:
        """Check if user role has permissions for specific context."""
        required_permissions = CONTEXT_PERMISSIONS.get(context, [])
        if additional_permissions:
            required_permissions.extend(additional_permissions)

        user_permissions = ROLE_PERMISSIONS.get(user_role, [])
        return all(perm in user_permissions for perm in required_permissions)

    def require_permission(self, permission: Permission):
        """Decorator to require specific permission."""

        def decorator(func):
            # Import here to avoid circular import
            from functools import wraps

            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Check if authentication is disabled (for development/testing)
                enable_auth = os.environ.get("ENABLE_AUTHENTICATION", "false").lower() == "true"

                if not enable_auth:
                    # Bypass authentication - use default admin user for development
                    kwargs["current_user"] = {
                        "user_id": "dev_user",
                        "username": "developer",
                        "role": "physician",
                        "full_name": "Development User",
                    }
                    return await func(*args, **kwargs)

                # Authentication enabled - require token
                from fastapi import Request

                request = None
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

                # Get token from Authorization header
                auth_header = None
                if request:
                    auth_header = request.headers.get("Authorization", "")

                if not auth_header or not auth_header.startswith("Bearer "):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Not authenticated",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

                token = auth_header.replace("Bearer ", "")
                user_data = self.verify_token(token)
                user_role = HealthcareRole(user_data.get("role"))

                if not self.check_permission(user_role, permission):
                    logger.warning(f"Permission denied: {user_role} lacks {permission}")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN, detail=f"Insufficient permissions: {permission} required"
                    )

                # Add user info to kwargs for downstream use
                kwargs["current_user"] = user_data
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    def require_context(self, context: str):
        """Decorator to require permissions for specific context."""

        def decorator(func):
            async def wrapper(*args, token: str = Depends(self.oauth2_scheme), **kwargs):
                user_data = self.verify_token(token)
                user_role = HealthcareRole(user_data.get("role"))

                if not self.check_context_permissions(user_role, context):
                    logger.warning(f"Context permission denied: {user_role} lacks access for {context}")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN, detail=f"Insufficient permissions for context: {context}"
                    )

                kwargs["current_user"] = user_data
                kwargs["access_context"] = context
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt."""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash."""
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except ValueError:
            return False

    def can_access_patient_record(
        self, user_role: HealthcareRole, user_id: str, patient_id: str, access_reason: str = "treatment"
    ) -> bool:
        """Check if user can access specific patient record."""
        # Basic role-based check
        if not self.check_permission(user_role, Permission.READ_PHI):
            if access_reason == "emergency" and self.check_permission(user_role, Permission.EMERGENCY_ACCESS):
                return True
            return False

        # In a real system, you would check:
        # - Provider-patient relationship
        # - Departmental access rights
        # - Consent permissions
        # - Minimum necessary principle

        return True

    def get_minimum_necessary_fields(
        self, user_role: HealthcareRole, access_context: str, requested_fields: List[str]
    ) -> List[str]:
        """Filter requested fields to minimum necessary for role and context."""
        # Define minimum necessary fields by role and context
        minimum_fields_map = {
            (HealthcareRole.PHYSICIAN, "patient_treatment"): [
                "patient_id",
                "name",
                "dob",
                "medical_history",
                "current_medications",
                "allergies",
                "vital_signs",
                "diagnosis",
                "treatment_plan",
            ],
            (HealthcareRole.NURSE, "patient_treatment"): [
                "patient_id",
                "name",
                "dob",
                "current_medications",
                "allergies",
                "vital_signs",
                "care_instructions",
            ],
            (HealthcareRole.RESEARCHER, "research"): [
                "anonymized_id",
                "age_range",
                "diagnosis",
                "treatment_outcome",
                "procedures_performed",
            ],
            (HealthcareRole.ADMINISTRATOR, "billing"): [
                "patient_id",
                "name",
                "insurance_info",
                "services_rendered",
                "charges",
            ],
        }

        minimum_fields = minimum_fields_map.get((user_role, access_context), [])

        # Filter requested fields to only those in minimum necessary
        allowed_fields = [field for field in requested_fields if field in minimum_fields]

        return allowed_fields

    def log_access_attempt(
        self,
        user_data: Dict[str, Any],
        resource: str,
        action: str,
        success: bool,
        additional_context: Dict[str, Any] = None,
    ):
        """Log access attempt for audit trail."""
        access_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_data.get("user_id"),
            "username": user_data.get("username"),
            "role": user_data.get("role"),
            "resource": resource,
            "action": action,
            "success": success,
            "ip_address": additional_context.get("ip_address") if additional_context else None,
            "user_agent": additional_context.get("user_agent") if additional_context else None,
        }

        if success:
            logger.info(f"Access granted: {access_log}")
        else:
            logger.warning(f"Access denied: {access_log}")

    def create_refresh_token(self, user_data: Dict[str, Any]) -> str:
        """Create refresh token for extended sessions."""
        to_encode = user_data.copy()
        expire = datetime.utcnow() + timedelta(days=7)  # Refresh tokens valid for 7 days
        to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh_token"})

        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def verify_refresh_token(self, token: str) -> Dict[str, Any]:
        """Verify refresh token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if payload.get("type") != "refresh_token":
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
            return payload
        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
