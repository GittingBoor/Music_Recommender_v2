"""Last.fm web-service client: track info, artist info, similar tracks."""
import json
import logging
import urllib.parse
import urllib.request

from src.metadata.cleaning import normalize_date, parse_featured_artists, strip_html

logger = logging.getLogger(__name__)

_LASTFM_BASE = "http://ws.audioscrobbler.com/2.0/"


def _lastfm_get(method: str, api_key: str, extra_params: dict[str, str]) -> dict | None:
    params = urllib.parse.urlencode({
        "method": method,
        "api_key": api_key,
        "format": "json",
        "autocorrect": 1,
        **extra_params,
    })
    try:
        with urllib.request.urlopen(f"{_LASTFM_BASE}?{params}", timeout=6) as resp:
            data = json.loads(resp.read().decode())
        if "error" in data:
            logger.warning("[Last.fm] %s → error %s: %s", method, data["error"], data.get("message"))
            return None
        return data
    except Exception as exc:
        logger.warning("[Last.fm] %s failed: %s", method, exc)
        return None


def fetch_track_info(title: str, artist: str, api_key: str) -> dict[str, object] | None:
    data = _lastfm_get("track.getInfo", api_key, {"artist": artist, "track": title})
    if not data:
        return None
    t = data.get("track", {})
    album = t.get("album") or {}
    artist_info = t.get("artist", {})
    artist_name = artist_info.get("name") if isinstance(artist_info, dict) else str(artist_info or "")
    wiki_published = (t.get("wiki") or {}).get("published", "") or ""
    track_title = t.get("name") or title
    return {
        "title": track_title,
        "artist": artist_name or None,
        "featured_artists": parse_featured_artists(track_title),
        "album": album.get("title") or None,
        "release_date": normalize_date(wiki_published),
        "playcount": int(t.get("playcount") or 0),
        "listeners": int(t.get("listeners") or 0),
        "mbid": t.get("mbid") or None,
        "url": t.get("url") or None,
    }


def fetch_artist_info(artist: str, api_key: str) -> dict[str, object] | None:
    data = _lastfm_get("artist.getInfo", api_key, {"artist": artist})
    if not data:
        return None
    a = data.get("artist", {})
    similar_raw = (a.get("similar") or {}).get("artist", [])
    if isinstance(similar_raw, dict):
        similar_raw = [similar_raw]
    bio_raw = (a.get("bio") or {}).get("summary", "") or ""
    stats = a.get("stats") or {}
    return {
        "artist_playcount": int(stats.get("playcount") or 0),
        "artist_listeners": int(stats.get("listeners") or 0),
        "artist_bio": strip_html(bio_raw) or None,
        "similar_artists": [s["name"] for s in similar_raw[:5] if isinstance(s, dict)],
    }


def fetch_similar_tracks(title: str, artist: str, api_key: str) -> list[dict] | None:
    data = _lastfm_get("track.getSimilar", api_key, {"artist": artist, "track": title, "limit": 5})
    if not data:
        return None
    tracks_raw = (data.get("similartracks") or {}).get("track", [])
    if isinstance(tracks_raw, dict):
        tracks_raw = [tracks_raw]
    result = []
    for t in tracks_raw[:5]:
        if not isinstance(t, dict):
            continue
        artist_field = t.get("artist")
        artist_name = artist_field.get("name") if isinstance(artist_field, dict) else str(artist_field or "")
        result.append({
            "title": t.get("name"),
            "artist": artist_name or None,
            "similarity": round(float(t.get("match") or 0), 4),
        })
    return result or None
