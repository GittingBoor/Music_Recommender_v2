import base64
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from mutagen import File as MutagenFile

logger = logging.getLogger(__name__)

_LASTFM_BASE = "http://ws.audioscrobbler.com/2.0/"
_MB_USERAGENT = ("MusicRecommender", "0.1", "user@example.com")
_mb_last_json_ts: float = 0.0

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
    if re.match(r'^\d{8}$', raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    if re.match(r'^\d{4}$', raw):
        return raw
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', raw)
    if m:
        day = m.group(1).zfill(2)
        mon = _MONTH_MAP.get(m.group(2).lower())
        year = m.group(3)
        return f"{year}-{mon}-{day}" if mon else year
    m = re.match(r'^(\d{4})[/.](\d{2})[/.](\d{2})$', raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r'\b(19|20)\d{2}\b', raw)
    return m.group(0) if m else None


def _parse_featured_artists(title: str) -> list[str]:
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
            logger.warning("[Last.fm] %s → error %s: %s", method, data["error"], data.get("message"))
            return None
        return data
    except Exception as exc:
        logger.warning("[Last.fm] %s failed: %s", method, exc)
        return None


# ── File tags ─────────────────────────────────────────────────────────────────

def extract_file_metadata(audio_path: Path) -> dict[str, object]:
    logger.info("[Metadata] Reading file tags: %s", audio_path.name)
    audio = MutagenFile(audio_path, easy=True)
    if audio is None:
        logger.warning("[Metadata] No tags readable from %s", audio_path.name)
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


# ── Last.fm ───────────────────────────────────────────────────────────────────

def _fetch_track_info(title: str, artist: str, api_key: str) -> dict[str, object] | None:
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
        "featured_artists": _parse_featured_artists(track_title),
        "album": album.get("title") or None,
        "release_date": _normalize_date(wiki_published),
        "playcount": int(t.get("playcount") or 0),
        "listeners": int(t.get("listeners") or 0),
        "mbid": t.get("mbid") or None,
        "url": t.get("url") or None,
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


# ── Spotify ───────────────────────────────────────────────────────────────────

def _spotify_get_token(client_id: str, client_secret: str) -> str | None:
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


def _fetch_spotify_info(title: str, artist: str, token: str) -> dict[str, object] | None:
    query = urllib.parse.urlencode({
        "q": f"track:{title} artist:{artist}",
        "type": "track",
        "limit": "1",
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

    track = tracks[0]
    album = track.get("album") or {}
    logger.info("[Spotify] Found: %r on %r (%s)", track.get("name"), album.get("name"), album.get("release_date"))
    return {
        "album": album.get("name") or None,
        "release_date": _normalize_date(album.get("release_date")),
        "spotify_id": track.get("id") or None,
    }


# ── MusicBrainz ───────────────────────────────────────────────────────────────

def _mb_json_get(path: str, params: dict[str, str]) -> dict | None:
    """
    Rate-limited direct JSON request to MusicBrainz web service.
    Respects the 1 request/second limit independently of musicbrainzngs calls.
    """
    global _mb_last_json_ts
    wait = 1.1 - (time.time() - _mb_last_json_ts)
    if wait > 0:
        time.sleep(wait)

    query = urllib.parse.urlencode({**params, "fmt": "json"})
    url = f"https://musicbrainz.org/ws/2/{path}?{query}"
    ua = f"{_MB_USERAGENT[0]}/{_MB_USERAGENT[1]} ( {_MB_USERAGENT[2]} )"
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        _mb_last_json_ts = time.time()
        return data
    except Exception as exc:
        logger.warning("[MusicBrainz] JSON API failed (%s): %s", type(exc).__name__, exc)
        _mb_last_json_ts = time.time()
        return None


def _acoustid_get_recording_id(audio_path: Path, api_key: str) -> str | None:
    try:
        import acoustid
    except ImportError:
        logger.warning("[AcoustID] pyacoustid not installed")
        return None

    logger.info("[AcoustID] Fingerprinting: %s", audio_path.name)
    try:
        matches = list(acoustid.match(api_key, str(audio_path)))
    except Exception as exc:
        logger.warning("[AcoustID] Failed (%s): %s", type(exc).__name__, exc)
        return None

    if not matches:
        logger.warning("[AcoustID] No matches for %s", audio_path.name)
        return None

    best = max(matches, key=lambda x: x[0])
    score = best[0]
    recording_id = best[1] if len(best) > 1 else None
    logger.info("[AcoustID] Best match: score=%.3f  recording_id=%s", score, recording_id)

    if score < 0.5:
        logger.warning("[AcoustID] Score %.3f below 0.5 — discarding", score)
        return None
    if not recording_id:
        logger.warning("[AcoustID] Match has no recording_id")
        return None
    return recording_id


def _mb_search_recording_ids(title: str, artist: str) -> list[str]:
    """Search MusicBrainz and return all candidate recording IDs ordered by score (>= 70)."""
    safe_title = title.replace('"', '').replace('\\', '')
    safe_artist = artist.replace('"', '').replace('\\', '')
    query = f'recording:"{safe_title}" AND artistname:"{safe_artist}"'
    logger.info("[MusicBrainz] JSON search: %s", query)

    data = _mb_json_get("recording", {"query": query, "limit": "10"})
    if not data:
        return []

    recordings: list[dict] = data.get("recordings") or []
    if not recordings:
        logger.warning("[MusicBrainz] JSON search: no results for %r / %r", artist, title)
        return []

    candidates = [r for r in recordings if int(r.get("score", 0)) >= 70]
    if not candidates:
        logger.warning("[MusicBrainz] All results below score 70")
        return []

    candidates.sort(key=lambda r: -int(r.get("score", 0)))
    logger.info("[MusicBrainz] %d candidate(s) found", len(candidates))
    for rec in candidates:
        logger.info(
            "[MusicBrainz]   Candidate: score=%s  id=%s  title=%r",
            rec.get("score"), rec.get("id"), rec.get("title"),
        )
    return [r["id"] for r in candidates]


def _mb_get_genres_for_recording(recording_id: str) -> list[str]:
    """Fetch genres from recording-level and release-group-level tags for one recording."""
    rec_data = _mb_json_get(f"recording/{recording_id}", {"inc": "tags"})
    recording_tags: list[dict] = (rec_data or {}).get("tags") or []
    logger.info("[MusicBrainz] Recording %s: %d tag(s)", recording_id, len(recording_tags))

    rg_tags: list[dict] = []
    rg_browse = _mb_json_get("release-group", {"recording": recording_id, "limit": "5"})
    if rg_browse:
        rgs: list[dict] = rg_browse.get("release-groups") or []
        if rgs:
            rg_id = rgs[0].get("id")
            if rg_id:
                rg_full = _mb_json_get(f"release-group/{rg_id}", {"inc": "tags"})
                rg_tags = (rg_full or {}).get("tags") or []
                logger.info("[MusicBrainz] Release-group %s: %d tag(s)", rg_id, len(rg_tags))

    seen: set[str] = set()
    merged: list[dict] = []
    for tag in recording_tags + rg_tags:
        name = (tag.get("name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            merged.append(tag)

    genres = [t["name"] for t in sorted(merged, key=lambda t: -int(t.get("count") or 0))][:10]
    logger.info("[MusicBrainz] Genres for %s: %s", recording_id, genres)
    return genres


def _fetch_musicbrainz_genres(
    audio_path: Path,
    acoustid_api_key: str,
    title: str = "",
    artist: str = "",
    lastfm_mbid: str = "",
) -> list[str]:
    """
    Resolve genres from MusicBrainz by iterating candidates until at least one genre is found.

    Priority:
    1. Last.fm MBID  — most reliable starting point
    2. AcoustID fingerprint — accurate when fpcalc + key available
    3. JSON text search — iterates through all score >= 70 candidates
    """
    try:
        import musicbrainzngs
    except ImportError:
        logger.warning("[MusicBrainz] musicbrainzngs not installed — skipping")
        return []

    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
    musicbrainzngs.set_useragent(*_MB_USERAGENT)

    # Step 1 — Last.fm MBID
    if lastfm_mbid:
        logger.info("[MusicBrainz] Trying Last.fm MBID: %s", lastfm_mbid)
        genres = _mb_get_genres_for_recording(lastfm_mbid)
        if genres:
            logger.info("[MusicBrainz] Genres via Last.fm MBID: %s", genres)
            return genres
        logger.warning("[MusicBrainz] Last.fm MBID yielded no genres — trying next source")

    # Step 2 — AcoustID fingerprint
    if acoustid_api_key:
        recording_id = _acoustid_get_recording_id(audio_path, acoustid_api_key)
        if recording_id:
            genres = _mb_get_genres_for_recording(recording_id)
            if genres:
                logger.info("[MusicBrainz] Genres via AcoustID: %s", genres)
                return genres
            logger.warning("[MusicBrainz] AcoustID recording yielded no genres")
    else:
        logger.info("[MusicBrainz] No ACOUSTID_API_KEY — skipping fingerprint")

    # Step 3 — JSON text search, iterate candidates
    if not title or not artist:
        logger.warning("[MusicBrainz] Cannot text-search — title or artist missing")
        return []

    recording_ids = _mb_search_recording_ids(title, artist)
    for i, recording_id in enumerate(recording_ids):
        logger.info("[MusicBrainz] Trying candidate %d/%d: %s", i + 1, len(recording_ids), recording_id)
        genres = _mb_get_genres_for_recording(recording_id)
        if genres:
            logger.info("[MusicBrainz] Genres via text search candidate %d: %s", i + 1, genres)
            return genres

    logger.warning("[MusicBrainz] No genres found across all candidates for %r / %r", artist, title)
    return []


# ── Main entry point ──────────────────────────────────────────────────────────

def extract_all_metadata(
    audio_path: Path,
    lastfm_api_key: str = "",
    acoustid_api_key: str = "",
    spotify_client_id: str = "",
    spotify_client_secret: str = "",
) -> dict[str, object]:
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

    # ── Last.fm ───────────────────────────────────────────────────────────────
    track_info: dict[str, object] | None = None
    artist_info: dict[str, object] = {}
    similar = None

    if not lastfm_api_key:
        logger.info("[Last.fm] Skipped — LASTFM_API_KEY not set")
    elif not title or not artist:
        logger.info("[Last.fm] Skipped — title or artist missing")
    else:
        logger.info("[Last.fm] Fetching: %r — %r", artist, title)
        track_info = _fetch_track_info(title, artist, lastfm_api_key)
        if track_info:
            artist_name = str(track_info.get("artist") or artist)
            artist_info = _fetch_artist_info(artist_name, lastfm_api_key) or {}
            similar = _fetch_similar_tracks(title, artist_name, lastfm_api_key)

            for field in ("title", "artist"):
                if not result.get(field) and track_info.get(field):
                    result[field] = track_info[field]
                    logger.info("[Last.fm] %s filled: %s", field, result[field])

            existing_featured: list[str] = list(result.get("featured_artists") or [])
            for fa in (track_info.get("featured_artists") or []):
                if fa not in existing_featured:
                    existing_featured.append(fa)
            result["featured_artists"] = existing_featured

    mb_title = str(result.get("title") or title)
    mb_artist = str(result.get("artist") or artist)
    lastfm_mbid = str(track_info.get("mbid") or "") if track_info else ""
    if lastfm_mbid:
        logger.info("[Metadata] Last.fm MBID for MB lookup: %s", lastfm_mbid)
    else:
        logger.info("[Metadata] No Last.fm MBID — will use AcoustID or text search")

    # ── Spotify (album + release_date) ────────────────────────────────────────
    if not spotify_client_id or not spotify_client_secret:
        logger.info("[Spotify] Skipped — SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET not set")
    elif not mb_title or not mb_artist:
        logger.info("[Spotify] Skipped — title or artist missing")
    else:
        logger.info("[Spotify] Fetching: %r — %r", mb_artist, mb_title)
        token = _spotify_get_token(spotify_client_id, spotify_client_secret)
        if token:
            spotify_info = _fetch_spotify_info(mb_title, mb_artist, token)
            if spotify_info:
                if spotify_info.get("album"):
                    result["album"] = spotify_info["album"]
                    logger.info("[Spotify] album: %s", result["album"])
                if spotify_info.get("release_date") and not result.get("release_date"):
                    result["release_date"] = spotify_info["release_date"]
                    logger.info("[Spotify] release_date: %s", result["release_date"])
            else:
                logger.warning("[Spotify] No info returned — falling back to Last.fm for album")
                if not result.get("album") and track_info and track_info.get("album"):
                    result["album"] = track_info["album"]
                    logger.info("[Last.fm] album fallback: %s", result["album"])
        else:
            logger.warning("[Spotify] Could not obtain token")
            if not result.get("album") and track_info and track_info.get("album"):
                result["album"] = track_info["album"]
                logger.info("[Last.fm] album fallback: %s", result["album"])

    # ── MusicBrainz (genres only) ─────────────────────────────────────────────
    genres = _fetch_musicbrainz_genres(
        audio_path, acoustid_api_key,
        title=mb_title, artist=mb_artist,
        lastfm_mbid=lastfm_mbid,
    )
    result["genres"] = genres
    result.setdefault("album_mbid", None)

    # ── Last.fm sub-dict ──────────────────────────────────────────────────────
    if track_info:
        lastfm_dict: dict[str, object] = {
            "playcount": track_info["playcount"],
            "listeners": track_info["listeners"],
            "mbid": track_info["mbid"],
            "url": track_info["url"],
            **artist_info,
        }
        if similar:
            lastfm_dict["similar_tracks"] = similar
        result["lastfm"] = lastfm_dict

    # ── Summary ───────────────────────────────────────────────────────────────
    _TRACKED = ("title", "artist", "album", "release_date", "genres", "album_mbid")
    found = [f for f in _TRACKED if result.get(f)]
    missing = [f for f in _TRACKED if not result.get(f)]
    logger.info("[Metadata] Summary — found: %s", found)
    if missing:
        logger.warning("[Metadata] Summary — NOT found: %s", missing)

    return result
