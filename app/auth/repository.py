"""Async database repository functions for user management."""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .models import User, async_session

logger = logging.getLogger(__name__)


async def create_user(
    email: str,
    hashed_password: str,
    full_name: str,
    role: str,
) -> Optional[User]:
    """Create a new user record.

    Args:
        email: User email address (must be unique).
        hashed_password: bcrypt-hashed password string.
        full_name: User's full display name.
        role: Healthcare role string (e.g. 'physician').

    Returns:
        The newly created User, or None if email already exists.
    """
    user = User(
        email=email,
        hashed_password=hashed_password,
        full_name=full_name,
        role=role,
    )
    async with async_session() as session:
        session.add(user)
        try:
            await session.commit()
            await session.refresh(user)
            return user
        except IntegrityError:
            await session.rollback()
            logger.warning("Attempted to create duplicate user: %s", email)
            return None


async def get_user_by_email(email: str) -> Optional[User]:
    """Fetch a user by email address.

    Args:
        email: Email address to look up.

    Returns:
        User instance or None if not found.
    """
    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalars().first()


async def get_user_by_id(user_id: int) -> Optional[User]:
    """Fetch a user by primary key.

    Args:
        user_id: Integer primary key.

    Returns:
        User instance or None if not found.
    """
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalars().first()
