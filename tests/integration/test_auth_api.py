"""Integration tests for POST /auth/login (mock accounts).

Runs against an in-process TestClient (no live server): the app lifespan seeds the
mock accounts into a tmp users.db.
"""

import pytest
from fastapi.testclient import TestClient

MOCK_DOCTOR = ("doctor@medvoice.local", "MedVoice2026!")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app.main import app
    from app.services import user_store

    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    with TestClient(app) as c:
        yield c


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
    from app.routers.auth import JWT_SECRET

    token = _login(client, *MOCK_DOCTOR).json()["access_token"]
    payload = jwt.decode(token, JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])
    assert payload["sub"].isdigit()
