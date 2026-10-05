from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.deps import get_db
from src.api.routes import auth as auth_route
from src.auth.password import hash_password, verify_password
from src.auth.session import SessionSigner
from src.core.config import Settings
from src.db.models.login_event import LoginEvent

_PASSWORD = "correct horse battery staple"
_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


class _FakeDb:
    """Collects added rows instead of writing to Postgres."""

    def __init__(self) -> None:
        self.added: list[LoginEvent] = []

    def add(self, row: LoginEvent) -> None:
        self.added.append(row)

    def commit(self) -> None:
        pass


# --- password hashing -------------------------------------------------------

def test_hash_roundtrip() -> None:
    stored = hash_password(_PASSWORD)
    assert "$" not in stored  # Compose would interpolate "$" in .env files
    assert verify_password(_PASSWORD, stored)
    assert not verify_password("wrong", stored)


def test_hash_uses_random_salt() -> None:
    assert hash_password(_PASSWORD) != hash_password(_PASSWORD)


def test_verify_rejects_malformed_hash() -> None:
    with pytest.raises(ValueError):
        verify_password(_PASSWORD, "not-a-hash")


# --- session tokens ---------------------------------------------------------

def test_token_valid_until_expiry() -> None:
    signer = SessionSigner(b"secret", timedelta(days=30))
    token = signer.issue(_NOW)
    assert signer.is_valid(token, _NOW + timedelta(days=29))
    assert not signer.is_valid(token, _NOW + timedelta(days=31))


def test_token_rejects_tampering_and_other_keys() -> None:
    signer = SessionSigner(b"secret", timedelta(days=30))
    token = signer.issue(_NOW)
    expires, signature = token.split(".")
    assert not signer.is_valid(f"{int(expires) + 999}.{signature}", _NOW)
    assert not SessionSigner(b"other", timedelta(days=30)).is_valid(token, _NOW)
    assert not signer.is_valid("garbage", _NOW)
    assert not signer.is_valid("", _NOW)


# --- routes -----------------------------------------------------------------

@pytest.fixture
def db() -> _FakeDb:
    return _FakeDb()


@pytest.fixture
def client(db: _FakeDb, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    settings = Settings(
        site_password_hash=hash_password(_PASSWORD),
        session_secret="test-secret",
        session_cookie_secure=False,
    )
    monkeypatch.setattr(auth_route, "settings", settings)
    app = FastAPI()
    app.include_router(auth_route.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_check_without_cookie_is_401(client: TestClient) -> None:
    assert client.get("/api/auth/check").status_code == 401


def test_wrong_password_is_401_and_logged(client: TestClient, db: _FakeDb) -> None:
    resp = client.post(
        "/api/auth/login",
        json={"password": "wrong"},
        headers={"CF-Connecting-IP": "203.0.113.7", "CF-IPCountry": "DE", "User-Agent": "TestUA"},
    )
    assert resp.status_code == 401
    assert "mr_session" not in resp.cookies
    assert client.get("/api/auth/check").status_code == 401
    [event] = db.added
    assert (event.success, event.ip, event.country, event.user_agent) == (False, "203.0.113.7", "DE", "TestUA")


def test_login_sets_session_and_device(client: TestClient, db: _FakeDb) -> None:
    resp = client.post("/api/auth/login", json={"password": _PASSWORD})
    assert resp.status_code == 204
    assert client.get("/api/auth/check").status_code == 204
    [event] = db.added
    assert event.success
    assert event.device_id == client.cookies.get("mr_device")
    assert len(event.device_id or "") == 32


def test_device_id_is_kept_across_logins(client: TestClient, db: _FakeDb) -> None:
    client.post("/api/auth/login", json={"password": "wrong"})
    client.post("/api/auth/login", json={"password": _PASSWORD})
    assert db.added[0].device_id == db.added[1].device_id


def test_logout_clears_session(client: TestClient) -> None:
    client.post("/api/auth/login", json={"password": _PASSWORD})
    client.post("/api/auth/logout")
    assert client.get("/api/auth/check").status_code == 401


def test_login_unconfigured_is_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_route, "settings", Settings(site_password_hash="", session_secret=""))
    assert client.post("/api/auth/login", json={"password": _PASSWORD}).status_code == 503
    assert client.get("/api/auth/check").status_code == 401
