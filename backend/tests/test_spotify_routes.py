import urllib.parse
from collections.abc import Generator, Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.api.routes import account as account_route
from src.api.routes import spotify as spotify_route
from src.core.config import settings
from src.db.models import (
    Base, PasswordResetToken, PlaylistImport, PlaylistImportTrack, Song, SpotifyConnection, User, UserPlaylist,
    UserPlaylistSong, generate_song_id,
)
from src.ingest.bulk import BulkItem
from src.spotify.client import PlaylistSummary, SpotifyApiError, TokenSet
from src.spotify.importer import PlaylistImporter
from src.spotify.matching import SpotifyTrack
from src.youtube.library_match import LibraryMatcher

_PASSWORD = "geheim-genug-123"
_PLAYLISTS = [PlaylistSummary(id="pl1", name="Mix", image=None, track_count=2, owner="benni")]
_TRACKS = [
    SpotifyTrack(spotify_id="t1", title="Hello", artists=("Adele",), duration_ms=295_000, isrc=None),
    SpotifyTrack(spotify_id="t2", title="Hey Brother", artists=("Avicii",), duration_ms=255_000, isrc=None),
]


class FakeClient:
    def __init__(self, me_error: int | None = None) -> None:
        self.me_error = me_error
        self.playlist_list = _PLAYLISTS
        self.liked: list[SpotifyTrack] | int = []

    def me(self) -> tuple[str, str | None]:
        if self.me_error:
            raise SpotifyApiError(self.me_error, "nope")
        return "benni-spotify", "Benni"

    def playlists(self) -> list[PlaylistSummary]:
        return self.playlist_list

    def playlist_tracks(self, playlist_id: str) -> list[SpotifyTrack]:
        assert playlist_id == "pl1"
        return _TRACKS

    def liked_tracks(self) -> list[SpotifyTrack]:
        if isinstance(self.liked, int):
            raise SpotifyApiError(self.liked, "nope")
        return self.liked


class Env:
    def __init__(self, factory: sessionmaker) -> None:
        self.factory = factory
        self.client = FakeClient()
        self.queued: list[BulkItem] = []
        self.importer = PlaylistImporter(factory, self._enqueue, lambda db: LibraryMatcher([("Hello", "Adele")]))

    def _enqueue(self, items: list[BulkItem]) -> int:
        self.queued.extend(items)
        return len(items)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    monkeypatch.setattr(settings, "session_secret", "test-secret")
    monkeypatch.setattr(settings, "session_cookie_secure", False)
    monkeypatch.setattr(settings, "spotify_client_id", "cid")
    monkeypatch.setattr(settings, "acoustid_api_key", "aid")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[
        User.__table__, PasswordResetToken.__table__, SpotifyConnection.__table__,
        PlaylistImport.__table__, PlaylistImportTrack.__table__, Song.__table__,
        UserPlaylist.__table__, UserPlaylistSong.__table__,
    ])
    yield Env(sessionmaker(bind=engine, autocommit=False, autoflush=False))
    engine.dispose()


@pytest.fixture
def client(env: Env) -> TestClient:
    def override_db() -> Generator[Session, None, None]:
        db = env.factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(account_route.router, prefix="/api")
    app.include_router(spotify_route.router, prefix="/api")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[spotify_route.get_importer] = lambda: env.importer
    app.dependency_overrides[spotify_route.get_client_factory] = lambda: (lambda connection, db: env.client)
    app.dependency_overrides[spotify_route.get_code_exchange] = lambda: (
        lambda code: TokenSet("access", "refresh", datetime.now(timezone.utc) + timedelta(hours=1))
    )
    return TestClient(app, follow_redirects=False)


def _login(client: TestClient, email: str = "benni@example.de") -> None:
    assert client.post("/api/account/register", json={"email": email, "password": _PASSWORD}).status_code == 201


def _connect(client: TestClient) -> None:
    start = client.get("/api/spotify/connect?next=/upload")
    state = urllib.parse.parse_qs(urllib.parse.urlparse(start.headers["location"]).query)["state"][0]
    done = client.get(f"/api/spotify/callback?code=abc&state={state}")
    assert done.headers["location"] == "/upload?spotify=connected"


def test_connect_requires_login(client: TestClient) -> None:
    resp = client.get("/api/spotify/connect")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/account?spotify=login"


def test_connect_redirects_to_spotify(client: TestClient) -> None:
    _login(client)
    resp = client.get("/api/spotify/connect")
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://accounts.spotify.com/authorize?")


def test_callback_rejects_bad_state(client: TestClient, env: Env) -> None:
    _login(client)
    client.get("/api/spotify/connect")
    resp = client.get("/api/spotify/callback?code=abc&state=forged")
    assert resp.headers["location"] == "/account?spotify=error"
    db = env.factory()
    assert db.query(SpotifyConnection).count() == 0
    db.close()


def test_callback_denied_by_user(client: TestClient) -> None:
    _login(client)
    client.get("/api/spotify/connect")
    resp = client.get("/api/spotify/callback?error=access_denied&state=x")
    assert resp.headers["location"] == "/account?spotify=denied"


def test_callback_user_not_allowlisted(client: TestClient, env: Env) -> None:
    _login(client)
    env.client = FakeClient(me_error=403)
    start = client.get("/api/spotify/connect")
    state = urllib.parse.parse_qs(urllib.parse.urlparse(start.headers["location"]).query)["state"][0]
    resp = client.get(f"/api/spotify/callback?code=abc&state={state}")
    assert resp.headers["location"] == "/account?spotify=not_allowed"


def test_callback_stores_connection(client: TestClient) -> None:
    _login(client)
    _connect(client)
    me = client.get("/api/account/me").json()
    assert me["spotify"] == {"spotify_user_id": "benni-spotify", "display_name": "Benni"}


def test_playlists_need_connection(client: TestClient) -> None:
    _login(client)
    assert client.get("/api/spotify/playlists").status_code == 409


def test_import_returns_counts(client: TestClient, env: Env) -> None:
    _login(client)
    _connect(client)
    resp = client.post("/api/spotify/playlists/pl1/import")
    assert resp.status_code == 202
    body = resp.json()
    assert (body["name"], body["total"], body["duplicate"], body["queued"]) == ("Mix", 2, 1, 1)
    assert [i.expected.spotify_id for i in env.queued] == ["t2"]

    env.queued[0].on_done({"status": "skipped", "reason": "no_fitting_hit"}, None)
    detail = client.get(f"/api/spotify/imports/{body['id']}").json()
    assert detail["failed"] == 1
    assert [(t["title"], t["status"], t["reason"]) for t in detail["tracks"]] == [
        ("Hello", "duplicate", None), ("Hey Brother", "failed", "no_fitting_hit"),
    ]
    assert detail["tracks"][1]["artists"] == ["Avicii"]
    playlists = client.get("/api/spotify/playlists").json()
    assert playlists[0]["last_import_id"] == body["id"]


def test_import_finishes_with_last_track(client: TestClient, env: Env) -> None:
    _login(client)
    _connect(client)
    body = client.post("/api/spotify/playlists/pl1/import").json()
    assert body["finished_at"] is None and body["finished_estimated"] is False

    env.queued[0].on_done({"status": "saved", "song_id": "abc"}, "vid")
    detail = client.get(f"/api/spotify/imports/{body['id']}").json()
    assert detail["finished_at"] is not None
    assert detail["finished_at"] >= detail["created_at"]
    assert detail["finished_estimated"] is False


def test_import_end_is_estimated_when_a_track_has_no_time(client: TestClient, env: Env) -> None:
    # Imports from before finished_at existed only know when some of their tracks ended.
    _login(client)
    _connect(client)
    body = client.post("/api/spotify/playlists/pl1/import").json()
    env.queued[0].on_done({"status": "skipped", "reason": "no_fitting_hit"}, None)
    db = env.factory()
    db.query(PlaylistImportTrack).filter(PlaylistImportTrack.status == "failed").update({"finished_at": None})
    db.commit()
    db.close()
    detail = client.get(f"/api/spotify/imports/{body['id']}").json()
    assert detail["finished_at"] is not None
    assert detail["finished_estimated"] is True


def test_retry_failed_queues_them_again(client: TestClient, env: Env) -> None:
    _login(client)
    _connect(client)
    body = client.post("/api/spotify/playlists/pl1/import").json()
    env.queued[0].on_done({"status": "skipped", "reason": "unverified"}, "vid")
    env.queued.clear()

    resp = client.post(f"/api/spotify/imports/{body['id']}/retry")
    assert resp.status_code == 202
    assert (resp.json()["failed"], resp.json()["queued"], resp.json()["finished_at"]) == (0, 1, None)
    assert [i.expected.spotify_id for i in env.queued] == ["t2"]

    env.queued[0].on_done({"status": "saved", "song_id": "s2"}, "vid2")
    detail = client.get(f"/api/spotify/imports/{body['id']}").json()
    assert (detail["saved"], detail["failed"], detail["queued"]) == (1, 0, 0)


def test_retry_needs_failed_tracks_and_own_import(client: TestClient, env: Env) -> None:
    _login(client)
    _connect(client)
    import_id = client.post("/api/spotify/playlists/pl1/import").json()["id"]
    assert client.post(f"/api/spotify/imports/{import_id}/retry").status_code == 409
    env.queued[0].on_done({"status": "skipped", "reason": "no_fitting_hit"}, None)
    client.post("/api/account/logout")
    _login(client, "other@example.de")
    assert client.post(f"/api/spotify/imports/{import_id}/retry").status_code == 404


def test_import_unknown_playlist_404(client: TestClient) -> None:
    _login(client)
    _connect(client)
    assert client.post("/api/spotify/playlists/foreign/import").status_code == 404


def test_imports_only_own(client: TestClient) -> None:
    _login(client)
    _connect(client)
    import_id = client.post("/api/spotify/playlists/pl1/import").json()["id"]
    client.post("/api/account/logout")
    _login(client, "other@example.de")
    assert client.get("/api/spotify/imports").json() == []
    assert client.get(f"/api/spotify/imports/{import_id}").status_code == 404


def test_disconnect(client: TestClient) -> None:
    _login(client)
    _connect(client)
    assert client.delete("/api/spotify/connection").status_code == 204
    assert client.get("/api/account/me").json()["spotify"] is None


# --- final review fixes -----------------------------------------------------------

def test_import_requires_acoustid(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)
    _connect(client)
    monkeypatch.setattr(settings, "acoustid_api_key", "")
    resp = client.post("/api/spotify/playlists/pl1/import")
    assert resp.status_code == 503
    assert "ACOUSTID_API_KEY" in resp.json()["detail"]


def test_resume_failure_does_not_stop_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> int:
        raise RuntimeError('relation "playlist_import_tracks" does not exist')

    monkeypatch.setattr(spotify_route._importer, "resume", broken)
    spotify_route.resume_playlist_imports()


def test_second_import_while_running_409(client: TestClient) -> None:
    _login(client)
    _connect(client)
    assert client.post("/api/spotify/playlists/pl1/import").status_code == 202
    resp = client.post("/api/spotify/playlists/pl1/import")
    assert resp.status_code == 409


def test_tokens_are_stored_encrypted(client: TestClient, env: Env) -> None:
    _login(client)
    _connect(client)
    db = env.factory()
    raw = db.execute(__import__("sqlalchemy").text("select access_token, refresh_token from spotify_connections")).one()
    connection = db.query(SpotifyConnection).one()
    db.close()
    assert raw[0] != "access" and raw[1] != "refresh"
    assert (connection.access_token, connection.refresh_token) == ("access", "refresh")


def test_spotify_outage_is_503_with_message(client: TestClient, env: Env) -> None:
    # Cloudflare replaces 502/504 from the origin with its own page, so the detail would be lost.
    _login(client)
    _connect(client)

    def down(playlist_id: str) -> list[SpotifyTrack]:
        raise SpotifyApiError(500, "boom")

    env.client.playlist_tracks = down  # type: ignore[method-assign]
    resp = client.post("/api/spotify/playlists/pl1/import")
    assert resp.status_code == 503
    assert "Spotify" in resp.json()["detail"]


# --- personal playlist view -------------------------------------------------------

def _add_song(env: Env, title: str, artist: str) -> str:
    db = env.factory()
    song_id = generate_song_id(title, artist)
    db.add(Song(id=song_id, title=title, artist=artist))
    db.commit()
    db.close()
    return song_id


def test_library_empty_when_logged_out(client: TestClient) -> None:
    assert client.get("/api/spotify/library").json() == []


def test_sync_matches_playlists_and_liked_songs(client: TestClient, env: Env) -> None:
    hello = _add_song(env, "Hello", "Adele")
    brother = _add_song(env, "Hey Brother", "Avicii")
    env.client.liked = [_TRACKS[1]]
    _login(client)
    _connect(client)

    body = client.post("/api/spotify/library/sync").json()
    assert body["liked_needs_reconnect"] is False
    assert [(p["kind"], p["name"], p["track_count"], p["song_ids"]) for p in body["playlists"]] == [
        ("liked", "Lieblingssongs", 1, [brother]),
        ("playlist", "Mix", 2, [hello, brother]),
    ]
    assert client.get("/api/spotify/library").json() == body["playlists"]


def test_sync_drops_deleted_playlists_and_reports_missing_scope(client: TestClient, env: Env) -> None:
    _login(client)
    _connect(client)
    client.post("/api/spotify/library/sync")
    env.client.playlist_list = []
    env.client.liked = 403

    body = client.post("/api/spotify/library/sync").json()
    assert body["liked_needs_reconnect"] is True
    assert [p["kind"] for p in body["playlists"]] == ["liked"]


def test_import_fills_the_library_view(client: TestClient, env: Env) -> None:
    hello = _add_song(env, "Hello", "Adele")
    _login(client)
    _connect(client)
    client.post("/api/spotify/playlists/pl1/import")
    assert client.get("/api/spotify/library").json()[0]["song_ids"] == [hello]

    brother = _add_song(env, "Hey Brother", "Avicii")
    env.queued[0].on_done({"status": "saved", "song_id": brother}, "vid")
    assert client.get("/api/spotify/library").json()[0]["song_ids"] == [hello, brother]
