import json
import logging
import re
import urllib.parse
import urllib.request
from pathlib import Path

from mutagen import File as MutagenFile

logger = logging.getLogger(__name__)

_LASTFM_BASE = "http://ws.audioscrobbler.com/2.0/"

_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def _tag_str(tags: object, key: str) -> str | None:
    value = tags.get(key) if tags else None
    if value is None:
        return None
    return str(value[0]) if isinstance(value, list) else str(value)


def _strip_html(text: str) -> str:
    text = re.sub(r'<a[^>]*>.*?</a>', '', text, flags=re.IGNORECASE)
    return re.sub(r'<[^>]+>', '', text).strip()


def _normalize_date(raw: str | None) -> str | None:
    """Normalize various date formats to YYYY-MM-DD or YYYY."""
    if not raw:
        return None
    raw = raw.strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', raw):
        return raw
    # YYYYMMDD
    if re.match(r'^\d{8}$', raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    # YYYY only
    if re.match(r'^\d{4}$', raw):
        return raw
    # "DD Mon YYYY, HH:MM" — Last.fm wiki.published format
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', raw)
    if m:
        day = m.group(1).zfill(2)
        mon = _MONTH_MAP.get(m.group(2).lower())
        year = m.group(3)
        return f"{year}-{mon}-{day}" if mon else year
    # YYYY/MM/DD or YYYY.MM.DD
    m = re.match(r'^(\d{4})[/.](\d{2})[/.](\d{2})$', raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # Fallback: year only
    m = re.search(r'\b(19|20)\d{2}\b', raw)
    return m.group(0) if m else None


def _parse_featured_artists(title: str) -> list[str]:
    """Extract featured artists from strings like 'Song (feat. A & B)'."""
    patterns = [
        r'\(feat\.?\s+([^)]+)\)',
        r'\(ft\.?\s+([^)]+)\)',
        r'\(featuring\s+([^)]+)\)',
        r'\bfeat\.?\s+([^(\[,]+)',
        r'\bft\.?\s+([^(\[,]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            artists_str = match.group(1).strip().rstrip(')')
            artists = re.split(r'\s*[&,]\s*|\s+x\s+|\s+and\s+', artists_str, flags=re.IGNORECASE)
            return [a.strip() for a in artists if a.strip()]
    return []


def _parse_title_artist_from_filename(audio_path: Path) -> tuple[str, str]:
    stem = audio_path.stem
    if " - " in stem:
        parts = stem.split(" - ", 1)
        return parts[1].strip(), parts[0].strip()
    return stem.strip(), ""


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
            logger.warning("[Metadata] Last.fm %s → error %s: %s", method, data["error"], data.get("message"))
            return None
        return data
    except Exception as exc:
        logger.warning("[Metadata] Last.fm %s failed: %s", method, exc)
        return None


def extract_file_metadata(audio_path: Path) -> dict[str, object]:
    logger.info("[Metadata] Reading file tags: %s", audio_path.name)
    audio = MutagenFile(audio_path, easy=True)
    if audio is None:
        logger.warning("[Metadata] No metadata readable from %s", audio_path.name)
        return {"filename": audio_path.name, "file_format": audio_path.suffix.lstrip(".").upper()}

    tags = audio.tags or {}
    genre_raw = _tag_str(tags, "genre")
    title = _tag_str(tags, "title")
    result: dict[str, object] = {
        "filename": audio_path.name,
        "title": title,
        "artist": _tag_str(tags, "artist"),
        "featured_artists": _parse_featured_artists(title) if title else [],
        "album": _tag_str(tags, "album"),
        "album_artist": _tag_str(tags, "albumartist"),
        "release_date": _normalize_date(_tag_str(tags, "date")),
        "genres": [genre_raw] if genre_raw else [],
        "file_format": audio_path.suffix.lstrip(".").upper(),
    }
    info = audio.info
    result["duration_seconds"] = round(float(info.length), 2)
    result["sample_rate_hz"] = getattr(info, "sample_rate", None)
    result["channels"] = getattr(info, "channels", None)
    bitrate = getattr(info, "bitrate", None)
    result["bitrate_kbps"] = round(bitrate / 1000) if bitrate else None
    return result


def _fetch_track_info(title: str, artist: str, api_key: str) -> dict[str, object] | None:
    data = _lastfm_get("track.getInfo", api_key, {"artist": artist, "track": title})
    if not data:
        return None
    t = data.get("track", {})
    tags_raw = t.get("toptags", {}).get("tag", [])
    if isinstance(tags_raw, dict):
        tags_raw = [tags_raw]
    album = t.get("album") or {}
    album_attr = album.get("@attr") or {}
    artist_info = t.get("artist", {})
    artist_name = artist_info.get("name") if isinstance(artist_info, dict) else str(artist_info or "")
    wiki_published = (t.get("wiki") or {}).get("published", "") or ""
    tag_names = [tag["name"] for tag in tags_raw if isinstance(tag, dict)][:10]
    track_title = t.get("name") or title
    return {
        "title": track_title,
        "artist": artist_name or None,
        "featured_artists": _parse_featured_artists(track_title),
        "album": album.get("title") or None,
        "album_artist": album.get("artist") or artist_name or None,
        "release_date": _normalize_date(wiki_published),
        "genres": tag_names,
        "playcount": int(t.get("playcount") or 0),
        "listeners": int(t.get("listeners") or 0),
        "mbid": t.get("mbid") or None,
        "url": t.get("url") or None,
        "album_mbid": album.get("mbid") or None,
    }


def _fetch_artist_info(artist: str, api_key: str) -> dict[str, object] | None:
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
        "artist_bio": _strip_html(bio_raw) or None,
        "similar_artists": [s["name"] for s in similar_raw[:5] if isinstance(s, dict)],
    }


def _fetch_similar_tracks(title: str, artist: str, api_key: str) -> list[dict] | None:
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


def extract_all_metadata(audio_path: Path, lastfm_api_key: str = "") -> dict[str, object]:
    file_meta = extract_file_metadata(audio_path)

    title = str(file_meta.get("title") or "")
    artist = str(file_meta.get("artist") or "")

    if not title or not artist:
        fn_title, fn_artist = _parse_title_artist_from_filename(audio_path)
        if not title and fn_title:
            title = fn_title
            logger.info("[Metadata] Title from filename: %s", title)
        if not artist and fn_artist:
            artist = fn_artist
            logger.info("[Metadata] Artist from filename: %s", artist)

    result = dict(file_meta)

    if not lastfm_api_key:
        logger.info("[Metadata] Last.fm skipped — LASTFM_API_KEY not set in .env")
        return result

    if not title or not artist:
        logger.info("[Metadata] Last.fm skipped — title or artist missing")
        return result

    logger.info("[Metadata] Fetching Last.fm data for: %s — %s", artist, title)
    track_info = _fetch_track_info(title, artist, lastfm_api_key)
    if not track_info:
        return result

    artist_name = str(track_info.get("artist") or artist)
    artist_info = _fetch_artist_info(artist_name, lastfm_api_key) or {}
    similar = _fetch_similar_tracks(title, artist_name, lastfm_api_key)

    # Fill missing top-level fields from Last.fm
    for field in ("title", "artist", "album", "album_artist", "release_date"):
        if not result.get(field) and track_info.get(field):
            result[field] = track_info[field]
            logger.info("[Metadata] %s filled from Last.fm: %s", field, result[field])

    # Merge featured_artists
    existing_featured: list[str] = list(result.get("featured_artists") or [])
    for fa in (track_info.get("featured_artists") or []):
        if fa not in existing_featured:
            existing_featured.append(fa)
    result["featured_artists"] = existing_featured

    # Merge genres (file tags + Last.fm tags, deduplicated, file tags first)
    existing_genres: list[str] = list(result.get("genres") or [])
    for g in (track_info.get("genres") or []):
        if g not in existing_genres:
            existing_genres.append(g)
    result["genres"] = existing_genres

    # Build lastfm-specific sub-dict (only what comes from Last.fm itself)
    lastfm_dict: dict[str, object] = {
        "playcount": track_info["playcount"],
        "listeners": track_info["listeners"],
        "genres": track_info["genres"],
        "mbid": track_info["mbid"],
        "url": track_info["url"],
        "album_mbid": track_info["album_mbid"],
        **artist_info,
    }
    if similar:
        lastfm_dict["similar_tracks"] = similar

    result["lastfm"] = lastfm_dict
    logger.info("[Metadata] Last.fm complete — %s plays, %s listeners", track_info.get("playcount"), track_info.get("listeners"))
    return result
