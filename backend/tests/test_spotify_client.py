import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from src.core.config import settings
from src.db.models import SpotifyConnection
from src.spotify.client import SpotifyApiError, SpotifyClient, authorize_url, exchange_code

_ME = "benni"


class FakeSpotify:
    """Answers Spotify API calls from a URL → response table and records each request."""

    def __init__(self, routes: dict[str, dict]) -> None:
        self.routes = routes
        self.requests: list[urllib.request.Request] = []
        self.fail_once: dict[str, int] = {}

    def __call__(self, req: urllib.request.Request) -> dict:
        self.requests.append(req)
        url = req.full_url
        if url in self.fail_once:
            raise SpotifyApiError(self.fail_once.pop(url), "expired")
        if url not in self.routes:
            raise AssertionError(f"unexpected request {url}")
        return self.routes[url]


def _connection(expires_in: timedelta = timedelta(hours=1)) -> SpotifyConnection:
    return SpotifyConnection(
        user_id=1, spotify_user_id=_ME, display_name="Benni",
        access_token="old-access", refresh_token="refresh-1",
        expires_at=datetime.now(timezone.utc) + expires_in,
    )


_TOKEN_URL = "https://accounts.spotify.com/api/token"
_REFRESHED = {"access_token": "new-access", "expires_in": 3600}


def _playlist(pid: str, owner: str, collaborative: bool = False, total: int = 3) -> dict:
    return {
        "id": pid, "name": f"List {pid}", "collaborative": collaborative,
        "owner": {"id": owner, "display_name": owner},
        "images": [{"url": f"https://img/{pid}"}], "items": {"total": total},
    }


def _track_entry(tid: str, name: str, *artists: str, local: bool = False, kind: str = "track") -> dict:
    return {"item": {
        "id": tid, "name": name, "type": kind, "is_local": local, "duration_ms": 200_000,
        "artists": [{"name": a} for a in artists], "external_ids": {"isrc": f"ISRC{tid}"},
    }}


def test_authorize_url_contains_scopes_and_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "spotify_client_id", "cid")
    monkeypatch.setattr(settings, "spotify_redirect_uri", "https://music.example.de/api/spotify/callback")
    url = urllib.parse.urlparse(authorize_url("state-123"))
    query = urllib.parse.parse_qs(url.query)
    assert url.netloc == "accounts.spotify.com" and url.path == "/authorize"
    assert query["client_id"] == ["cid"]
    assert query["response_type"] == ["code"]
    assert query["state"] == ["state-123"]
    assert query["redirect_uri"] == ["https://music.example.de/api/spotify/callback"]
    assert set(query["scope"][0].split()) == {"playlist-read-private", "playlist-read-collaborative", "user-library-read"}


def test_exchange_code_returns_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "spotify_client_id", "cid")
    monkeypatch.setattr(settings, "spotify_client_secret", "secret")
    fake = FakeSpotify({_TOKEN_URL: {"access_token": "a", "refresh_token": "r", "expires_in": 3600}})
    tokens = exchange_code("the-code", send=fake)
    assert (tokens.access_token, tokens.refresh_token) == ("a", "r")
    assert tokens.expires_at > datetime.now(timezone.utc) + timedelta(minutes=59)
    body = urllib.parse.parse_qs(fake.requests[0].data.decode())
    assert body["grant_type"] == ["authorization_code"] and body["code"] == ["the-code"]
    assert fake.requests[0].get_header("Authorization").startswith("Basic ")


def test_playlists_filters_foreign() -> None:
    first = "https://api.spotify.com/v1/me/playlists?limit=50"
    second = "https://api.spotify.com/v1/me/playlists?limit=50&offset=50"
    fake = FakeSpotify({
        first: {"items": [_playlist("own", _ME), _playlist("foreign", "spotify")], "next": second},
        second: {"items": [_playlist("collab", "friend", collaborative=True, total=7)], "next": None},
    })
    playlists = SpotifyClient(_connection(), save=lambda c: None, send=fake).playlists()
    assert [p.id for p in playlists] == ["own", "collab"]
    assert playlists[1].track_count == 7
    assert playlists[0].image == "https://img/own"
    assert fake.requests[0].get_header("Authorization") == "Bearer old-access"


def test_playlist_tracks_paginates_and_skips_local() -> None:
    first = "https://api.spotify.com/v1/playlists/p1/items?limit=50"
    second = "https://api.spotify.com/v1/playlists/p1/items?limit=50&offset=50"
    fake = FakeSpotify({
        first: {"items": [
            _track_entry("t1", "Stay", "The Kid LAROI", "Justin Bieber"),
            _track_entry("t2", "My Local File", "Me", local=True),
            _track_entry("e1", "Some Episode", "Podcaster", kind="episode"),
            {"item": None},
        ], "next": second},
        second: {"items": [{"track": _track_entry("t3", "Hello", "Adele")["item"]}], "next": None},
    })
    tracks = SpotifyClient(_connection(), save=lambda c: None, send=fake).playlist_tracks("p1")
    assert [t.spotify_id for t in tracks] == ["t1", "t3"]
    assert tracks[0].artists == ("The Kid LAROI", "Justin Bieber")
    assert tracks[0].duration_ms == 200_000 and tracks[0].isrc == "ISRCt1"


def test_client_refreshes_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "spotify_client_id", "cid")
    monkeypatch.setattr(settings, "spotify_client_secret", "secret")
    me = "https://api.spotify.com/v1/me"
    fake = FakeSpotify({_TOKEN_URL: _REFRESHED, me: {"id": _ME, "display_name": "Benni"}})
    saved: list[SpotifyConnection] = []
    connection = _connection(expires_in=timedelta(seconds=10))

    assert SpotifyClient(connection, save=saved.append, send=fake).me() == (_ME, "Benni")
    assert fake.requests[0].full_url == _TOKEN_URL
    assert fake.requests[1].get_header("Authorization") == "Bearer new-access"
    assert saved and saved[0].access_token == "new-access"
    assert connection.refresh_token == "refresh-1"  # Spotify sent no new one: keep the old


def test_client_refreshes_after_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "spotify_client_id", "cid")
    monkeypatch.setattr(settings, "spotify_client_secret", "secret")
    me = "https://api.spotify.com/v1/me"
    fake = FakeSpotify({_TOKEN_URL: {**_REFRESHED, "refresh_token": "refresh-2"}, me: {"id": _ME}})
    fake.fail_once[me] = 401
    connection = _connection()
    assert SpotifyClient(connection, save=lambda c: None, send=fake).me() == (_ME, None)
    assert connection.refresh_token == "refresh-2"


def test_client_raises_other_errors() -> None:
    me = "https://api.spotify.com/v1/me"
    fake = FakeSpotify({})
    fake.fail_once[me] = 403
    with pytest.raises(SpotifyApiError) as info:
        SpotifyClient(_connection(), save=lambda c: None, send=fake).me()
    assert info.value.status == 403


def test_non_numeric_retry_after_is_an_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.spotify import client as client_module

    def fake_urlopen(req, timeout):  # noqa: ANN001
        raise client_module.urllib.error.HTTPError(req.full_url, 429, "Too Many", {"Retry-After": "Wed, 21 Oct"}, None)

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(client_module.time, "sleep", lambda s: None)
    with pytest.raises(SpotifyApiError) as info:
        client_module._http_send(urllib.request.Request("https://api.spotify.com/v1/me"))
    assert info.value.status == 429


def test_transient_server_error_is_retried_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.spotify import client as client_module

    class Ok:
        def __enter__(self) -> "Ok":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self) -> bytes:
            return b'{"id": "benni"}'

    answers: list[object] = [
        client_module.urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None), Ok(),
    ]

    def fake_urlopen(req, timeout):  # noqa: ANN001
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(client_module.time, "sleep", lambda s: None)
    assert client_module._http_send(urllib.request.Request("https://api.spotify.com/v1/me")) == {"id": "benni"}
    assert answers == []
