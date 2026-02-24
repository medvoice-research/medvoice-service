"""SQLAlchemy async User model for authentication (PostgreSQL)."""

import os
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

# Read POSTGRES_URL from environment (same database used by the Next.js frontend).
_raw_url = os.environ.get(
    "POSTGRES_URL",
    "postgresql://postgres:postgres@localhost:5432/medvoice_portal",
)
# Normalise the legacy 'postgres://' scheme before swapping in the async driver.
if _raw_url.startswith("postgres://"):
    _raw_url = _raw_url.replace("postgres://", "postgresql://", 1)
AUTH_DB_URL = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

async_engine = create_async_engine(
    AUTH_DB_URL,
    echo=False,
)

async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
)

Base = declarative_base()


class User(Base):
    """User model for authentication storage."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_active = Column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email!r}, role={self.role!r})>"


async def init_auth_db() -> None:
    """Create the users table if it does not exist."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
