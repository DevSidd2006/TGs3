import sqlite3
from datetime import timedelta
from pathlib import Path

from app.db import ensure_schema
from app.repository import AuthRepository


def make_repo(tmp_path: Path) -> AuthRepository:
    connection = sqlite3.connect(tmp_path / "auth.db", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    return AuthRepository(connection)


def test_create_and_verify_user(tmp_path):
    repo = make_repo(tmp_path)
    repo.upsert_user(username="admin", password_hash="hash-1")
    assert repo.verify_user("admin", "hash-1") is True
    assert repo.verify_user("admin", "hash-2") is False
    assert repo.verify_user("nobody", "hash-1") is False


def test_upsert_user_updates_existing(tmp_path):
    repo = make_repo(tmp_path)
    repo.upsert_user(username="admin", password_hash="hash-1")
    repo.upsert_user(username="admin", password_hash="hash-2")
    assert repo.verify_user("admin", "hash-2") is True
    assert repo.verify_user("admin", "hash-1") is False


def test_session_create_and_validate(tmp_path):
    repo = make_repo(tmp_path)
    repo.upsert_user(username="admin", password_hash="hash-1")
    token = repo.create_session(username="admin", ttl=timedelta(days=1))
    assert repo.get_session_user(token) == "admin"


def test_session_expired_or_unknown_returns_none(tmp_path):
    repo = make_repo(tmp_path)
    assert repo.get_session_user("missing-token") is None
    token = repo.create_session(username="admin", ttl=timedelta(days=-1))
    assert repo.get_session_user(token) is None


def test_delete_session_invalidates_token(tmp_path):
    repo = make_repo(tmp_path)
    repo.upsert_user(username="admin", password_hash="hash-1")
    token = repo.create_session(username="admin", ttl=timedelta(days=1))
    repo.delete_session(token)
    assert repo.get_session_user(token) is None
