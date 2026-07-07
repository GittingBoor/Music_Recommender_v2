"""Spotify web-API client: album name and release date via track search."""
import base64
import json
import logging
import urllib.parse
import urllib.request

from src.metadata.cleaning import better_date, normalize_date, title_similar

logger = logging.getLogger(__name__)

_ALBUM_TYPE_RANK: dict[str, int] = {"album": 0, "single": 1, "ep": 2, "compilation": 3}


def get_token(client_id: str, client_secret: str) -> str | None:
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=data,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return json.loads(resp.read().decode()).get("access_token")
    except Exception as exc:
        logger.warning("[Spotify] Token request failed: %s", exc)
        return None


def fetch_spotify_info(title: str, artist: str, token: str) -> dict[str, object] | None:
    query = urllib.parse.urlencode({
        "q": f"track:{title} artist:{artist}",
        "type": "track",
        "limit": "5",
    })
    req = urllib.request.Request(
        f"https://api.spotify.com/v1/search?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        logger.warning("[Spotify] Search failed: %s", exc)
        return None

    tracks = (data.get("tracks") or {}).get("items") or []
    if not tracks:
        logger.warning("[Spotify] No results for %r / %r", artist, title)
        return None

    logger.info("[Spotify] Search returned %d result(s) for %r / %r", len(tracks), artist, title)
    for i, t in enumerate(tracks):
        t_album = t.get("album") or {}
        t_artists = [a.get("name") for a in (t.get("artists") or []) if isinstance(a, dict)]
        logger.info(
            "[Spotify] [%d/%d] title=%r  artists=%s  album=%r  release_date=%s  "
            "date_precision=%s  album_type=%s  id=%s",
            i + 1, len(tracks),
            t.get("name"), t_artists,
            t_album.get("name"), t_album.get("release_date"),
            t_album.get("release_date_precision"), t_album.get("album_type"),
            t.get("id"),
        )

    matches: list[dict] = [
        c for c in tracks if title_similar(title, c.get("name") or "")
    ]
    if not matches:
        logger.warning(
            "[Spotify] No title match found — searched %r, candidates: %s",
            title, [t.get("name") for t in tracks],
        )
        return None

    # Album name: prefer original album release (album > single > ep > compilation).
    # Release date: pick the earliest full (day-precision) date across all matches.
    def _album_sort_key(t: dict) -> tuple[int, str]:
        alb = t.get("album") or {}
        type_rank = _ALBUM_TYPE_RANK.get(alb.get("album_type") or "", 99)
        date = alb.get("release_date") or "9999"
        return (type_rank, date)

    matches.sort(key=_album_sort_key)
    track = matches[0]  # best album type, earliest date within that type

    # Earliest full date across ALL matches, regardless of album type
    earliest_full: str | None = None
    for m in matches:
        alb_m = m.get("album") or {}
        d = alb_m.get("release_date") or ""
        if alb_m.get("release_date_precision") == "day" and len(d) == 10:
            earliest_full = better_date(earliest_full or "", d) or earliest_full

    album = track.get("album") or {}

    all_artists: list[dict] = track.get("artists") or []
    featured_artists: list[str] = [
        a["name"] for a in all_artists[1:] if isinstance(a, dict) and a.get("name")
    ]
    logger.info(
        "[Spotify] %d match(es) — album pick: %r on %r (%s, type=%s)  "
        "earliest_full_date=%s  featured=%s",
        len(matches), track.get("name"), album.get("name"), album.get("release_date"),
        album.get("album_type"), earliest_full, featured_artists,
    )
    return {
        "album": album.get("name") or None,
        "release_date": normalize_date(earliest_full),
        "spotify_id": track.get("id") or None,
        "featured_artists": featured_artists,
    }
