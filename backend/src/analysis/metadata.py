import json
import logging
import re
import urllib.parse
import urllib.request
from pathlib import Path

from mutagen import File as MutagenFile

logger = logging.getLogger(__name__)

_LASTFM_BASE = "http://ws.audioscrobbler.com/2.0/"


def _tag_str(tags: object, key: str) -> str | None:
    """Safely extract a string value from a mutagen easy-tag dict."""
    value = tags.get(key) if tags else None
    if value is None:
        return None
    return str(value[0]) if isinstance(value, list) else str(value)


def _strip_html(text: str) -> str:
    """Remove HTML tags and trailing Last.fm read-more links from a string."""
    text = re.sub(r'<a[^>]*>.*?</a>', '', text, flags=re.IGNORECASE)
    return re.sub(r'<[^>]+>', '', text).strip()


def _parse_title_artist_from_filename(audio_path: Path) -> tuple[str, str]:
    """Extract title and artist from 'Artist - Title' filename pattern."""
    stem = audio_path.stem
    if " - " in stem:
        parts = stem.split(" - ", 1)
        return parts[1].strip(), parts[0].strip()
    return stem.strip(), ""


def _lastfm_get(method: str, api_key: str, extra_params: dict[str, str]) -> dict | None:
    """Execute a Last.fm API request and return parsed JSON, or None on failure."""
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
            logger.warning("[Metadata] Last.fm %s → error %s: %s", method, data["error"], data.get("message"))
            return None
        return data
    except Exception as exc:
        logger.warning("[Metadata] Last.fm %s failed: %s", method, exc)
        return None


def extract_file_metadata(audio_path: Path) -> dict[str, object]:
    """Extract tags and stream info from an audio file via mutagen."""
    logger.info("[Metadata] Reading file tags: %s", audio_path.name)
    audio = MutagenFile(audio_path, easy=True)
    if audio is None:
        logger.warning("[Metadata] No metadata readable from %s", audio_path.name)
        return {"file_format": audio_path.suffix.lstrip(".").upper()}

    tags = audio.tags or {}
    result: dict[str, object] = {
        "title": _tag_str(tags, "title"),
        "artist": _tag_str(tags, "artist"),
        "album": _tag_str(tags, "album"),
        "album_artist": _tag_str(tags, "albumartist"),
        "year": _tag_str(tags, "date"),
        "genre_tag": _tag_str(tags, "genre"),
        "track_number": _tag_str(tags, "tracknumber"),
        "composer": _tag_str(tags, "composer"),
        "comment": _tag_str(tags, "comment"),
        "file_format": audio_path.suffix.lstrip(".").upper(),
    }
    info = audio.info
    result["duration_seconds"] = round(float(info.length), 2)
    result["sample_rate_hz"] = getattr(info, "sample_rate", None)
    result["channels"] = getattr(info, "channels", None)
    bitrate = getattr(info, "bitrate", None)
    result["bitrate_kbps"] = round(bitrate / 1000) if bitrate else None
    return result


def _parse_year(published: str) -> str | None:
    """Extract 4-digit year from Last.fm wiki.published string like '01 Jan 2020, 00:00'."""
    match = re.search(r'\b(19|20)\d{2}\b', published)
    return match.group(0) if match else None


def _fetch_track_info(title: str, artist: str, api_key: str) -> dict[str, object] | None:
    """Fetch track.getInfo and return structured result."""
    data = _lastfm_get("track.getInfo", api_key, {"artist": artist, "track": title})
    if not data:
        return None
    t = data.get("track", {})
    tags_raw = t.get("toptags", {}).get("tag", [])
    if isinstance(tags_raw, dict):
        tags_raw = [tags_raw]
    album = t.get("album", {})
    album_attr = album.get("@attr", {})
    artist_name = t.get("artist", {}).get("name") if isinstance(t.get("artist"), dict) else t.get("artist")
    wiki_published = t.get("wiki", {}).get("published", "") or ""
    tag_names = [tag["name"] for tag in tags_raw][:5]
    return {
        "title": t.get("name"),
        "artist": artist_name,
        "album": album.get("title") or None,
        "album_artist": album.get("artist") or artist_name or None,
        "track_number": album_attr.get("position") or None,
        "year": _parse_year(wiki_published),
        "genre_tag": tag_names[0] if tag_names else None,
        "playcount": int(t.get("playcount", 0)),
        "listeners": int(t.get("listeners", 0)),
        "tags": tag_names,
        "mbid": t.get("mbid") or None,
        "url": t.get("url") or None,
        "album_mbid": album.get("mbid") or None,
    }


def _fetch_artist_info(artist: str, api_key: str) -> dict[str, object] | None:
    """Fetch artist.getInfo and return bio, similar artists, and stats."""
    data = _lastfm_get("artist.getInfo", api_key, {"artist": artist})
    if not data:
        return None
    a = data.get("artist", {})
    similar_raw = a.get("similar", {}).get("artist", [])
    if isinstance(similar_raw, dict):
        similar_raw = [similar_raw]
    bio_raw = a.get("bio", {}).get("summary", "") or ""
    return {
        "artist_playcount": int(a.get("stats", {}).get("playcount", 0)),
        "artist_listeners": int(a.get("stats", {}).get("listeners", 0)),
        "artist_bio": _strip_html(bio_raw) or None,
        "similar_artists": [s["name"] for s in similar_raw[:5]],
    }


def _fetch_similar_tracks(title: str, artist: str, api_key: str) -> list[dict] | None:
    """Fetch track.getSimilar and return top-5 similar tracks."""
    data = _lastfm_get("track.getSimilar", api_key, {"artist": artist, "track": title, "limit": 5})
    if not data:
        return None
    tracks_raw = data.get("similartracks", {}).get("track", [])
    if isinstance(tracks_raw, dict):
        tracks_raw = [tracks_raw]
    return [
        {
            "title": t.get("name"),
            "artist": t.get("artist", {}).get("name"),
            "similarity": round(float(t.get("match", 0)), 4),
        }
        for t in tracks_raw[:5]
    ]


def fetch_lastfm_metadata(title: str, artist: str, api_key: str) -> dict[str, object] | None:
    """Fetch and combine track info, artist info, and similar tracks from Last.fm."""
    if not api_key:
        logger.info("[Metadata] Last.fm skipped — LASTFM_API_KEY not set in .env")
        return None
    if not title or not artist:
        logger.info("[Metadata] Last.fm skipped — title or artist missing (title=%r, artist=%r)", title, artist)
        return None

    logger.info("[Metadata] Fetching Last.fm data for: %s — %s", artist, title)

    track_info = _fetch_track_info(title, artist, api_key)
    if not track_info:
        return None

    artist_name = track_info.get("artist") or artist
    artist_info = _fetch_artist_info(artist_name, api_key) or {}
    similar = _fetch_similar_tracks(title, artist_name, api_key)

    result = {**track_info, **artist_info}
    if similar:
        result["similar_tracks"] = similar

    logger.info("[Metadata] Last.fm complete — %s plays, %s listeners", result.get("playcount"), result.get("listeners"))
    return result


def extract_all_metadata(audio_path: Path, lastfm_api_key: str = "") -> dict[str, object]:
    """Extract file metadata and enrich with Last.fm data. Fills null tags from Last.fm."""
    file_meta = extract_file_metadata(audio_path)

    title = file_meta.get("title") or ""
    artist = file_meta.get("artist") or ""

    if not title or not artist:
        fn_title, fn_artist = _parse_title_artist_from_filename(audio_path)
        if not title and fn_title:
            title = fn_title
            logger.info("[Metadata] Title from filename: %s", title)
        if not artist and fn_artist:
            artist = fn_artist
            logger.info("[Metadata] Artist from filename: %s", artist)

    lastfm = fetch_lastfm_metadata(title=title, artist=artist, api_key=lastfm_api_key)

    result = dict(file_meta)

    if lastfm:
        for field in ("title", "artist", "album", "album_artist", "year", "genre_tag", "track_number"):
            if not result.get(field) and lastfm.get(field):
                result[field] = lastfm.get(field)
                logger.info("[Metadata] %s filled from Last.fm: %s", field, result[field])
        result["lastfm"] = lastfm

    return result
