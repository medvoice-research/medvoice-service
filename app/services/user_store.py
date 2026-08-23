"""SQLite store for login users + idempotent mock-account seeding (mock auth POC).

Separate DB file from patient_mappings.db so DB_FRESH_START can never wipe accounts.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import bcrypt

from ..config import Config
from ..logger import logger

DB_PATH = Path(Config.USERS_DB_PATH).resolve()

MOCK_USERS = [
    {"email": "doctor@medvoice.local", "password": "MedVoice2026!", "full_name": "Dr. Demo", "role": "physician"},
    {"email": "nurse@medvoice.local", "password": "MedVoice2026!", "full_name": "Nurse Demo", "role": "nurse"},
    {"email": "admin@medvoice.local", "password": "Admin2026!", "full_name": "Admin Demo", "role": "admin"},
]


@contextmanager
def get_db_connection():
    """Context manager for user-database connections (mirrors app.patients.database)."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"User database error: {str(e)}")
        raise
    finally:
        conn.close()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        # bcrypt rejects secrets over 72 bytes; no seeded hash can match one.
        return False


def init_user_store() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'physician',
                created_at TEXT NOT NULL
            )
        """)
    logger.info(f"User store initialized at {DB_PATH}")


def seed_mock_accounts() -> None:
    """Create MOCK_USERS when the table is empty; no-op otherwise (idempotent)."""
    if count_users() > 0:
        return
    for account in MOCK_USERS:
        create_user(
            email=account["email"],
            password_hash=hash_password(account["password"]),
            full_name=account["full_name"],
            role=account["role"],
        )
    logger.info(f"Seeded {len(MOCK_USERS)} mock accounts")


def count_users() -> int:
    with get_db_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return int(row["n"]) if row else 0


def get_user_by_email(email: str) -> Optional[dict]:
    """Case-insensitive lookup; returns {id, email, password_hash, full_name, role} or None."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, full_name, role FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
        return dict(row) if row else None


def create_user(email: str, password_hash: str, full_name: str, role: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, full_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (email.strip().lower(), password_hash, full_name, role, now),
        )
        return int(cursor.lastrowid)
