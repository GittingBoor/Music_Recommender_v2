"""Spotify Web API on behalf of a user: OAuth (authorization code flow), playlists, tracks.

Development-mode rules since Feb 2026: playlist contents are only returned for
playlists the user owns or collaborates on, so other playlists are not listed.
"""
import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.core.config import settings
from src.db.models import SpotifyConnection
from src.spotify.matching import SpotifyTrack

logger = logging.getLogger(__name__)

_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API = "https://api.spotify.com/v1"
# user-library-read (saved tracks) came later: older connections lack it until reconnected.
SCOPES = "playlist-read-private playlist-read-collaborative user-library-read"
_PAGE_SIZE = 50
_TIMEOUT_SECONDS = 15
# Renew this long before the access token runs out, so no call races the expiry.
_REFRESH_MARGIN = timedelta(seconds=60)
_MAX_RETRY_AFTER_SECONDS = 30
# Spotify's own hiccups; a second try a moment later usually goes through.
_TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})
_TRANSIENT_RETRY_SECONDS = 2


class SpotifyApiError(Exception):
    """Spotify answered with an HTTP error (``status``) or could not be reached (status 0)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Spotify HTTP {status}: {message}")
        self.status = status


Sender = Callable[[urllib.request.Request], dict]


def _retry_after_seconds(header: str | None) -> int:
    """Seconds from a Retry-After header; an HTTP date or garbage counts as one second."""
    try:
        return max(int(header or 1), 1)
    except ValueError:
        return 1


def _http_send(req: urllib.request.Request) -> dict:
    """Send once more after a 429 (Spotify's rate limit names the wait) or a 5xx hiccup."""
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                body = resp.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt == 0:
                wait = min(_retry_after_seconds(exc.headers.get("Retry-After")), _MAX_RETRY_AFTER_SECONDS)
                logger.warning("[Spotify] Rate limited, retrying in %ds", wait)
                time.sleep(wait)
                continue
            if exc.code in _TRANSIENT_STATUSES and attempt == 0:
                logger.warning("[Spotify] HTTP %d, retrying in %ds", exc.code, _TRANSIENT_RETRY_SECONDS)
                time.sleep(_TRANSIENT_RETRY_SECONDS)
                continue
            raise SpotifyApiError(exc.code, exc.read().decode(errors="replace")[:300]) from exc
        except OSError as exc:
            raise SpotifyApiError(0, str(exc)) from exc
    raise SpotifyApiError(429, "rate limited or unavailable twice")


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_at: datetime


@dataclass(frozen=True)
class PlaylistSummary:
    id: str
    name: str
    image: str | None
    track_count: int
    owner: str | None


def authorize_url(state: str) -> str:
    """Where to send the browser so the user can allow access to their playlists."""
    query = urllib.parse.urlencode({
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": SCOPES,
        "state": state,
    })
    return f"{_AUTHORIZE_URL}?{query}"


def _token_request(form: dict[str, str], send: Sender) -> TokenSet:
    credentials = base64.b64encode(f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()).decode()
    req = urllib.request.Request(
        _TOKEN_URL,
        data=urllib.parse.urlencode(form).encode(),
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    data = send(req)
    return TokenSet(
        access_token=str(data["access_token"]),
        refresh_token=data.get("refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in") or 3600)),
    )


def exchange_code(code: str, send: Sender = _http_send) -> TokenSet:
    """Trade the callback's ``code`` for access and refresh token."""
    return _token_request(
        {"grant_type": "authorization_code", "code": code, "redirect_uri": settings.spotify_redirect_uri}, send,
    )


def refresh(refresh_token: str, send: Sender = _http_send) -> TokenSet:
    return _token_request({"grant_type": "refresh_token", "refresh_token": refresh_token}, send)


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


class SpotifyClient:
    """API calls for one connected user; renews the access token and hands it to ``save``."""

    def __init__(
        self, connection: SpotifyConnection, save: Callable[[SpotifyConnection], None], send: Sender = _http_send,
    ) -> None:
        self._connection = connection
        self._save = save
        self._send = send

    def _refresh(self) -> None:
        tokens = refresh(self._connection.refresh_token, self._send)
        self._connection.access_token = tokens.access_token
        self._connection.expires_at = tokens.expires_at
        if tokens.refresh_token:
            self._connection.refresh_token = tokens.refresh_token
        self._save(self._connection)

    def _get(self, url: str) -> dict:
        if _as_utc(self._connection.expires_at) - _REFRESH_MARGIN <= datetime.now(timezone.utc):
            self._refresh()
        try:
            return self._send(self._authorised(url))
        except SpotifyApiError as exc:
            if exc.status != 401:
                raise
        self._refresh()
        return self._send(self._authorised(url))

    def _authorised(self, url: str) -> urllib.request.Request:
        return urllib.request.Request(url, headers={"Authorization": f"Bearer {self._connection.access_token}"})

    def _pages(self, url: str) -> list[dict]:
        items: list[dict] = []
        next_url: str | None = url
        while next_url:
            page = self._get(next_url)
            items.extend(page.get("items") or [])
            next_url = page.get("next")
        return items

    def me(self) -> tuple[str, str | None]:
        """``(spotify user id, display name)`` of the connected account."""
        data = self._get(f"{_API}/me")
        return str(data["id"]), data.get("display_name")

    def playlists(self) -> list[PlaylistSummary]:
        """The user's own and collaborative playlists (the only ones Spotify shows the songs of)."""
        own = self._connection.spotify_user_id
        return [
            _to_summary(p) for p in self._pages(f"{_API}/me/playlists?limit={_PAGE_SIZE}")
            if p and ((p.get("owner") or {}).get("id") == own or p.get("collaborative"))
        ]

    def playlist_tracks(self, playlist_id: str) -> list[SpotifyTrack]:
        """Every music track of the playlist in order; local files and podcast episodes are left out."""
        quoted = urllib.parse.quote(playlist_id, safe="")
        entries = self._pages(f"{_API}/playlists/{quoted}/items?limit={_PAGE_SIZE}")
        tracks = (_to_track(e.get("item") or e.get("track")) for e in entries if e)
        return [t for t in tracks if t is not None]

    def liked_tracks(self) -> list[SpotifyTrack]:
        """The user's saved tracks, newest first. 403 without the user-library-read scope."""
        entries = self._pages(f"{_API}/me/tracks?limit={_PAGE_SIZE}")
        tracks = (_to_track(e.get("track")) for e in entries if e)
        return [t for t in tracks if t is not None]


def _to_summary(playlist: dict) -> PlaylistSummary:
    # The Feb 2026 API renamed the playlist's "tracks" field to "items".
    counts = playlist.get("items") or playlist.get("tracks") or {}
    images = playlist.get("images") or []
    owner = playlist.get("owner") or {}
    return PlaylistSummary(
        id=str(playlist["id"]),
        name=str(playlist.get("name") or ""),
        image=images[0].get("url") if images else None,
        track_count=int(counts.get("total") or 0),
        owner=owner.get("display_name") or owner.get("id"),
    )


def _to_track(item: dict | None) -> SpotifyTrack | None:
    if not item or item.get("type") != "track" or item.get("is_local") or not item.get("id"):
        return None
    artists = tuple(a["name"] for a in item.get("artists") or [] if a.get("name"))
    if not item.get("name") or not artists:
        return None
    return SpotifyTrack(
        spotify_id=str(item["id"]),
        title=str(item["name"]),
        artists=artists,
        duration_ms=item.get("duration_ms"),
        isrc=(item.get("external_ids") or {}).get("isrc"),
    )
