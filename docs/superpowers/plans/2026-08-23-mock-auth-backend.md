# Mock Auth Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /auth/login` on medvoice-service backed by a seeded SQLite users table, so the MedVoice app can log in with mock accounts.

**Architecture:** New `user_store.py` (SQLite at data/users.db, bcrypt hashes) + new `auth.py` router (python-jose JWT). Seeded idempotently at startup. Additive only — no existing endpoint changes, ENABLE_AUTHENTICATION stays false.

**Tech Stack:** FastAPI, passlib[bcrypt], python-jose[cryptography] (both already in pyproject), sqlite3 stdlib, pytest.

Spec: `docs/superpowers/specs/2026-08-23-mock-auth-login-design.md`

---

### Task 1: User store

**Files:**
- Create: `app/services/user_store.py`
- Modify: `app/config.py` (add USERS_DB_PATH next to PATIENT_DB_PATH)
- Test: `tests/unit/test_user_store.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the mock-auth user store."""
import sqlite3

import pytest

from app.services import user_store


@pytest.fixture()
def fresh_store(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    user_store.init_user_store()
    yield


def test_seed_mock_accounts_is_idempotent(fresh_store):
    user_store.seed_mock_accounts()
    user_store.seed_mock_accounts()
    assert user_store.count_users() == len(user_store.MOCK_USERS)


def test_get_user_by_email_is_case_insensitive(fresh_store):
    user_store.seed_mock_accounts()
    user = user_store.get_user_by_email("DOCTOR@medvoice.local")
    assert user is not None
    assert user["email"] == "doctor@medvoice.local"


def test_password_hashes_are_bcrypt_and_not_recoverable(fresh_store):
    from passlib.context import CryptContext

    user_store.seed_mock_accounts()
    user = user_store.get_user_by_email("doctor@medvoice.local")
    assert user["password_hash"].startswith("$2")
    assert "MedVoice2026!" not in user["password_hash"]
    assert CryptContext(schemes=["bcrypt"]).verify("MedVoice2026!", user["password_hash"])


def test_missing_user_returns_none(fresh_store):
    assert user_store.get_user_by_email("nobody@x.local") is None


def test_db_file_lives_in_data_dir_not_patient_db():
    from app.config import Config

    assert str(Config.USERS_DB_PATH).endswith("users.db")
    assert Config.USERS_DB_PATH != Config.PATIENT_DB_PATH
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_user_store.py -v`
Expected: FAIL — `ModuleNotFoundError`/`AttributeError` (no user_store module / no USERS_DB_PATH).

- [ ] **Step 3: Write minimal implementation**

`app/config.py` — add directly below the `PATIENT_DB_PATH = ...` line:

```python
    USERS_DB_PATH = _get_yaml("database", "users_db_path", "./data/users.db")
```

`app/services/user_store.py`:

```python
"""SQLite store for login users + idempotent mock-account seeding (mock auth POC)."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from passlib.context import CryptContext

from ..config import Config
from ..logger import logger

DB_PATH = Path(Config.USERS_DB_PATH).resolve()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

MOCK_USERS = [
    {"email": "doctor@medvoice.local", "password": "MedVoice2026!", "full_name": "Dr. Demo", "role": "physician"},
    {"email": "nurse@medvoice.local", "password": "MedVoice2026!", "full_name": "Nurse Demo", "role": "nurse"},
    {"email": "admin@medvoice.local", "password": "Admin2026!", "full_name": "Admin Demo", "role": "admin"},
]


def init_user_store() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'physician',
                created_at TEXT NOT NULL
            )
            """
        )
    logger.info(f"User store initialized at {DB_PATH}")


def seed_mock_accounts() -> None:
    """Create MOCK_USERS when the table is empty; no-op otherwise (idempotent)."""
    if count_users() > 0:
        return
    for account in MOCK_USERS:
        create_user(
            email=account["email"],
            password_hash=pwd_context.hash(account["password"]),
            full_name=account["full_name"],
            role=account["role"],
        )
    logger.info(f"Seeded {len(MOCK_USERS)} mock accounts")


def count_users() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return int(row["n"]) if row else 0


def get_user_by_email(email: str) -> Optional[dict]:
    """Case-insensitive lookup; returns {id, email, password_hash, full_name, role} or None."""
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, email, password_hash, full_name, role FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
        return dict(row) if row else None


def create_user(email: str, password_hash: str, full_name: str, role: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, full_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (email.strip().lower(), password_hash, full_name, role, now),
        )
        return int(cursor.lastrowid)


class _Connect(sqlite3.Connection):
    """Row factory + commit-on-success context manager."""


def _connect() -> _Connect:
    raise NotImplementedError  # replaced below by get_db_connection-style helper


def get_db_connection():
    ...
```

NOTE for implementer: do NOT copy the `_Connect` sketch above — follow the project's existing
pattern in `app/patients/database.py`: module-level `@contextmanager def get_db_connection()`
yielding a `sqlite3.connect(str(DB_PATH))` connection with `row_factory = sqlite3.Row`,
commit on success / rollback on error / close in finally. All public functions use it.
The tests patch `user_store.DB_PATH`, so every connection must go through `DB_PATH`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_user_store.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/user_store.py app/config.py tests/unit/test_user_store.py
git commit -m "feat(auth): SQLite user store with bcrypt hashing + mock-account seeding"
```

---

### Task 2: Auth router

**Files:**
- Create: `app/routers/auth.py`
- Modify: `app/main.py` (include router + startup seeding hook)
- Test: `tests/integration/test_auth_api.py`

- [ ] **Step 1: Write the failing test**

Look at `tests/integration/test_recordings_api.py` first and reuse its client fixture pattern
(how it builds a FastAPI TestClient against `app.main.app`). Then:

```python
"""Integration tests for POST /auth/login (mock accounts)."""

MOCK_DOCTOR = ("doctor@medvoice.local", "MedVoice2026!")


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_login_with_valid_mock_account_returns_token_and_user(client):
    response = _login(client, *MOCK_DOCTOR)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and len(body["access_token"]) > 20
    assert body["user"]["email"] == "doctor@medvoice.local"
    assert body["user"]["role"] == "physician"
    assert "password" not in body["user"] and "password_hash" not in body["user"]


def test_all_three_mock_accounts_can_log_in(client):
    for email, pw in [
        ("doctor@medvoice.local", "MedVoice2026!"),
        ("nurse@medvoice.local", "MedVoice2026!"),
        ("admin@medvoice.local", "Admin2026!"),
    ]:
        assert _login(client, email, pw).status_code == 200


def test_wrong_password_returns_401_envelope(client):
    response = _login(client, MOCK_DOCTOR[0], "wrong-password")
    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_credentials"


def test_unknown_email_returns_same_401_as_wrong_password(client):
    wrong_pw = _login(client, MOCK_DOCTOR[0], "wrong-password")
    unknown = _login(client, "ghost@nowhere.local", "whatever")
    assert unknown.status_code == 401
    assert unknown.json() == wrong_pw.json()


def test_malformed_body_returns_422(client):
    response = client.post("/auth/login", json={"email": "not-an-email"})
    assert response.status_code == 422


def test_issued_token_decodes_to_user_id(client):
    from jose import jwt

    from app.config import Config

    token = _login(client, *MOCK_DOCTOR).json()["access_token"]
    payload = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=[Config.JWT_ALGORITHM])
    assert payload["sub"].isdigit()
```

If the repo's conftest lacks an auth-friendly `client` fixture that runs app startup
(seeding), create one in this file: build `TestClient(app)` after pointing
`user_store.DB_PATH` at a tmp_path via monkeypatch BEFORE importing/calling startup.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_auth_api.py -v`
Expected: FAIL — 404 (route doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

`app/routers/auth.py`:

```python
"""Auth API — POST /auth/login for the mobile-app mock accounts."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr

from ..config import Config
from ..services.user_store import get_user_by_email

router = APIRouter(tags=["Auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    email: EmailStr
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
    def __init__(self, status_code: int, detail: str, error_code: str):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


@router.post("/auth/login", summary="Log in with email + password (mock accounts)")
async def login(body: LoginRequest) -> LoginResponse:
    user = get_user_by_email(body.email)
    if not user or not pwd_context.verify(body.password, user["password_hash"]):
        raise AuthError(401, "Invalid email or password", "invalid_credentials")

    expires = datetime.now(timezone.utc) + timedelta(minutes=Config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    token = jwt.encode(
        {"sub": str(user["id"]), "exp": expires},
        Config.JWT_SECRET_KEY,
        algorithm=Config.JWT_ALGORITHM,
    )
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserPublic(id=user["id"], email=user["email"], full_name=user["full_name"], role=user["role"]),
    )
```

Implementer notes:
- If `EmailStr` needs `email-validator` and it's absent, fall back to
  `email: str` plus a minimal regex check returning 422 via `raise HTTPException(422, ...)`
  inside the handler — but CHECK pyproject first; prefer EmailStr if the dep exists.
- `Config.JWT_SECRET_KEY` may be None in dev. In that case generate once:
  `secrets.token_hex(32)` stored module-level, and log a warning. Do not crash startup.

`app/main.py`:
- Import `auth` alongside the other routers and add `app.include_router(auth.router)`
  with the existing include block.
- In the existing startup/lifespan hook (find where `init_database` or similar init calls run;
  if there is none, add a `@app.on_event("startup")` matching the codebase's FastAPI version style),
  call:

```python
from app.services import user_store

user_store.init_user_store()
user_store.seed_mock_accounts()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_auth_api.py tests/unit/test_user_store.py -v`
Expected: PASS

- [ ] **Step 5: Run the whole suite to prove nothing broke**

Run: `uv run pytest tests/ -x -q --ignore=tests/scripts` (or whatever invocation tests/README.md documents)
Expected: same pass/fail set as before your change (note pre-existing failures if any).

- [ ] **Step 6: Commit**

```bash
git add app/routers/auth.py app/main.py tests/integration/test_auth_api.py
git commit -m "feat(auth): POST /auth/login with JWT + seeded mock accounts"
```

---

### Task 3: Env config alignment

**Files:**
- Modify: `.env` line 21 → `LM_STUDIO_MODEL=bio-medical-llama-3-8b`

- [ ] **Step 1:** Edit `.env` (do not echo other lines; .env is gitignored).
- [ ] **Step 2:** No commit (.env is gitignored).
