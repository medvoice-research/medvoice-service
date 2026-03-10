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
    """Create a new user record."""
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
    """Fetch a user by email address."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalars().first()


async def get_user_by_id(user_id: int) -> Optional[User]:
    """Fetch a user by primary key."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalars().first()
