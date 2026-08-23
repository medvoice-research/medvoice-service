"""Unit tests for the mock-auth user store."""

import bcrypt
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
    user_store.seed_mock_accounts()
    user = user_store.get_user_by_email("doctor@medvoice.local")
    assert user["password_hash"].startswith("$2")
    assert "MedVoice2026!" not in user["password_hash"]
    assert bcrypt.checkpw(b"MedVoice2026!", user["password_hash"].encode())
    assert user_store.verify_password("MedVoice2026!", user["password_hash"])
    assert not user_store.verify_password("wrong", user["password_hash"])


def test_missing_user_returns_none(fresh_store):
    assert user_store.get_user_by_email("nobody@x.local") is None


def test_db_file_lives_in_data_dir_not_patient_db():
    from app.config import Config

    assert str(Config.USERS_DB_PATH).endswith("users.db")
    assert Config.USERS_DB_PATH != Config.PATIENT_DB_PATH
