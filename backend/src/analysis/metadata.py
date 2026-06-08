import base64
import difflib
import json
import logging
import re
import time
import urllib.error
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

# Patterns inside () or [] that are video/platform noise and not part of the real title.
# Covers YouTube upload conventions, quality labels, release variants, and platform markers.
_NOISE_BRACKET_RE = re.compile(
    r'\s*[\(\[]\s*(?:'
    # Official variants
    r'official\s*(?:music\s+)?(?:video|audio|lyric(?:s)?\s*video?|lyrics?|visuali[sz]er|clip|'
    r'performance(?:\s+video)?|live(?:\s+video)?|mv)?\b|'
    r'official\s*artist\s*channel|'
    # Video type
    r'music\s*video|video\s*clip|lyric(?:s)?\s*video|lyrics?|audio|visuali[sz]er|'
    # Quality / resolution
    r'full\s*hd|hd|hq|4k|2160p|1440p|1080p|720p|480p|360p|'
    # Remaster variants (with optional year)
    r'(?:(?:19|20)\d{2}\s*)?remaster(?:ed)?(?:\s+(?:19|20)\d{2})?|'
    # Platform / distribution markers
    r'auto[\s\-]?generated|ncs\s*(?:release)?|vevo|'
    # Standalone year
    r'(?:19|20)\d{2}'
    r')[^\)\]]*[\)\]]',
    re.IGNORECASE,
)

# "Artist - Song - Official Video"  →  strip " - Official Video" suffix
_TRAILING_DASH_NOISE_RE = re.compile(
    r'\s+-\s+(?:official\s*(?:music\s+)?(?:video|audio|lyrics?|clip|mv)?|'
    r'music\s*video|lyrics?|audio|visuali[sz]er|hd|hq|4k)\s*$',
    re.IGNORECASE,
)

# YouTube auto-generated: "Song | Artist - Topic"  or  "Song | Official Video"
_PIPE_NOISE_RE = re.compile(
    r'\s*\|\s*(?:official\s*(?:music\s+)?(?:video|audio|mv)?|'
    r'music\s*video|lyrics?|audio|visuali[sz]er|'
    r'.+?\s*-\s*topic)\s*$',
    re.IGNORECASE,
)


def _clean_title(text: str) -> str:
    """Remove common YouTube/video-upload noise from a song title or artist string."""
    text = _NOISE_BRACKET_RE.sub("", text)
    text = _TRAILING_DASH_NOISE_RE.sub("", text)
    text = _PIPE_NOISE_RE.sub("", text)
    return text.strip(" -_.")


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
        r'\[feat\.?\s+([^\]]+)\]',
        r'\[ft\.?\s+([^\]]+)\]',
        r'\[featuring\s+([^\]]+)\]',
        r'\bfeat\.?\s+([^(\[,\]]+)',
        r'\bft\.?\s+([^(\[,\]]+)',
        r'\bfeaturing\s+([^(\[,\]]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            artists_str = match.group(1).strip().rstrip(')]')
            artists = re.split(r'\s*[&,]\s*|\s+x\s+|\s+and\s+', artists_str, flags=re.IGNORECASE)
            return [a.strip().rstrip('])') for a in artists if a.strip()]
    return []


def _dedup_featured_artists(artists: list[str]) -> list[str]:
    """Deduplicate featured artists, keeping the longer/more complete name when one is a substring of another."""
    if not artists:
        return artists
    normalized = [a.lower().strip() for a in artists]
    kept: list[str] = []
    for i, (n, original) in enumerate(zip(normalized, artists)):
        # Skip if a longer version already exists (e.g. "Pharrell" when "Pharrell Williams" is present)
        dominated = any(
            j != i and n in normalized[j] and len(normalized[j]) > len(n)
            for j in range(len(normalized))
        )
        if not dominated and original not in kept:
            kept.append(original)
    return kept


_FEAT_IN_ARTIST_RE = re.compile(
    r'\s*(?:feat\.?|ft\.?|featuring)\s+.+$',
    re.IGNORECASE,
)


def _split_artist_featuring(artist_str: str) -> tuple[str, list[str]]:
    """Split 'David Guetta Feat. Kid Cudi' → ('David Guetta', ['Kid Cudi'])."""
    featured = _parse_featured_artists(artist_str)
    if not featured:
        return artist_str, []
    clean = _FEAT_IN_ARTIST_RE.sub("", artist_str).strip()
    return clean, featured


def _parse_title_artist_from_filename(audio_path: Path) -> tuple[str, str]:
    stem = audio_path.stem
    if " - " in stem:
        parts = stem.split(" - ", 1)
        return _clean_title(parts[1].strip()), parts[0].strip()
    return _clean_title(stem.strip()), ""


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

    # Always clean feat./ft. from the artist tag so the main artist is stored cleanly
    raw_artist = _tag_str(tags, "artist")
    clean_artist, feat_from_artist = _split_artist_featuring(raw_artist or "") if raw_artist else (raw_artist, [])

    feat_from_title = _parse_featured_artists(title) if title else []
    all_featured: list[str] = list(feat_from_artist)
    for fa in feat_from_title:
        if fa not in all_featured:
            all_featured.append(fa)
    all_featured = _dedup_featured_artists(all_featured)

    result: dict[str, object] = {
        "filename": audio_path.name,
        "title": title,
        "artist": clean_artist,
        "featured_artists": all_featured,
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

def _title_similar(queried: str, returned: str, threshold: float = 0.6) -> bool:
    """Return True if the Spotify-returned title is close enough to what we searched for.

    Normalise both strings (lowercase, strip punctuation) then accept if:
    - one is a substring of the other, OR
    - SequenceMatcher ratio >= threshold
    """
    def normalise(s: str) -> str:
        return re.sub(r"[^\w\s]", "", s.lower()).strip()

    q = normalise(queried)
    r = normalise(returned)
    if not q or not r:
        return False
    if q in r or r in q:
        return True
    return difflib.SequenceMatcher(None, q, r).ratio() >= threshold


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
        c for c in tracks if _title_similar(title, c.get("name") or "")
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
            earliest_full = _better_date(earliest_full or "", d) or earliest_full

    album = track.get("album") or {}
    date_precision: str = album.get("release_date_precision") or "unknown"

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
        "release_date": _normalize_date(earliest_full),
        "spotify_id": track.get("id") or None,
        "featured_artists": featured_artists,
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


_ACOUSTID_ERROR_CODES: dict[int, str] = {
    1: "unknown format",
    2: "missing parameter",
    3: "invalid fingerprint",
    4: "invalid API key",
    5: "internal server error",
    6: "invalid user API key",
    13: "service unavailable",
    14: "too many requests (rate limited)",
    17: "unknown application",
    18: "fingerprint not found in database",
}


def _acoustid_probe_key(api_key: str) -> None:
    """Make a minimal direct request to AcoustID to surface the real error code.

    pyacoustid's parse_lookup_result only raises WebServiceError("status: error")
    and throws away the actual error JSON — this function reads it directly.
    Only called once when a WebServiceError is already observed.
    """
    params = urllib.parse.urlencode({
        "client": api_key,
        "meta": "recordings",
        "duration": "1",
        "fingerprint": "AQAAA",  # minimal dummy — will fail with code 3 if key is valid
    }).encode()
    req = urllib.request.Request(
        "https://api.acoustid.org/v2/lookup",
        data=params,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as http_exc:
        # AcoustID returns 4xx with a JSON body — read it from the error response.
        try:
            data = json.loads(http_exc.read().decode())
        except Exception:
            logger.warning("[AcoustID] Probe failed — HTTP %s, unreadable body", http_exc.code)
            return
    except Exception as exc:
        logger.warning("[AcoustID] Probe failed — %s: %s", type(exc).__name__, exc)
        return

    status = data.get("status")
    if status == "ok":
        logger.info("[AcoustID] API key is valid (probe returned ok)")
        return

    error = data.get("error") or {}
    code: int = error.get("code", 0)
    message: str = error.get("message") or status or "unknown"
    description = _ACOUSTID_ERROR_CODES.get(code, "")
    if description:
        logger.error("[AcoustID] Server error — code %d: %s (%s)", code, message, description)
    else:
        logger.error("[AcoustID] Server error — code %d: %s", code, message)

    if code == 4:
        logger.error(
            "[AcoustID] The ACOUSTID_API_KEY is invalid. "
            "Register an application at https://acoustid.org/login and set the key in .env"
        )
    elif code == 14:
        logger.warning("[AcoustID] Rate limited — too many requests")


def _acoustid_get_metadata(
    audio_path: Path, api_key: str
) -> tuple[str | None, str | None, str | None]:
    """Fingerprint via AcoustID and return (recording_id, title, artist).

    All three values may be None on failure or low confidence.
    The title/artist come directly from the AcoustID/MusicBrainz response and
    reflect the canonical song name — useful as a fallback when the filename
    contains noise like '(Official Video)'.
    """
    try:
        import acoustid
    except ImportError:
        logger.warning("[AcoustID] pyacoustid not installed")
        return None, None, None

    # Step 1: generate fingerprint separately so we can log what's actually sent.
    logger.info("[AcoustID] Fingerprinting: %s", audio_path.name)
    try:
        duration, fingerprint = acoustid.fingerprint_file(str(audio_path))
        logger.info(
            "[AcoustID] Fingerprint ready — duration=%.1fs  fp_length=%d chars",
            duration, len(fingerprint) if fingerprint else 0,
        )
    except acoustid.FingerprintGenerationError as exc:
        logger.warning("[AcoustID] Fingerprint generation failed: %s", exc)
        return None, None, None
    except Exception as exc:
        logger.warning("[AcoustID] Fingerprint step failed (%s): %s", type(exc).__name__, exc)
        return None, None, None

    if not fingerprint or duration <= 0:
        logger.warning(
            "[AcoustID] Empty fingerprint or zero duration (duration=%.1f) — skipping lookup",
            duration,
        )
        return None, None, None

    # Step 2: raw lookup with sources so we can pick the most-voted recording.
    params = urllib.parse.urlencode({
        "client": api_key,
        "meta": "recordings sources",
        "duration": str(int(duration)),
        "fingerprint": fingerprint,
    }).encode()
    req = urllib.request.Request(
        "https://api.acoustid.org/v2/lookup",
        data=params,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        _acoustid_probe_key(api_key)
        logger.warning("[AcoustID] HTTP %s during lookup", exc.code)
        return None, None, None
    except Exception as exc:
        logger.warning("[AcoustID] Lookup failed (%s): %s", type(exc).__name__, exc)
        return None, None, None

    if data.get("status") != "ok":
        logger.warning("[AcoustID] Non-ok status: %s", data.get("status"))
        return None, None, None

    results: list[dict] = data.get("results") or []
    if not results:
        logger.warning("[AcoustID] No matches for %s", audio_path.name)
        return None, None, None

    # Take the highest-scored result above the threshold.
    best_result = max(results, key=lambda r: r.get("score", 0.0))
    score: float = float(best_result.get("score", 0.0))
    if score < 0.5:
        logger.warning("[AcoustID] Best score %.3f below 0.5 — discarding", score)
        return None, None, None

    recordings: list[dict] = best_result.get("recordings") or []
    if not recordings:
        logger.warning("[AcoustID] Score %.3f match has no linked recordings", score)
        return None, None, None

    # Pick the recording with the most sources (community votes).
    # Titles without parentheses are preferred as a tiebreaker.
    def _rec_sort_key(rec: dict) -> tuple[int, int]:
        sources = int(rec.get("sources") or 0)
        title = rec.get("title") or ""
        no_parens = 0 if re.search(r'\(', title) else 1
        return (sources, no_parens)

    recordings_sorted = sorted(recordings, key=_rec_sort_key, reverse=True)
    best_rec = recordings_sorted[0]

    logger.info(
        "[AcoustID] %d recording(s) for score=%.3f — picked by sources:",
        len(recordings), score,
    )
    for rec in recordings_sorted:
        artists_raw = rec.get("artists") or []
        rec_artist = ", ".join(
            a if isinstance(a, str) else a.get("name", "?") for a in artists_raw
        )
        logger.info(
            "[AcoustID]   sources=%-3s  %s  title=%r  artist=%r",
            rec.get("sources"), "← chosen" if rec is best_rec else "        ",
            rec.get("title"), rec_artist,
        )

    recording_id: str | None = best_rec.get("id")
    aid_title: str | None = best_rec.get("title")
    artists_raw = best_rec.get("artists") or []
    aid_artist: str | None = ", ".join(
        a if isinstance(a, str) else a.get("name", "?") for a in artists_raw
    ) or None

    if not recording_id:
        logger.warning("[AcoustID] No MusicBrainz recording_id — title/artist from user metadata only")

    return recording_id, aid_title, aid_artist


def _acoustid_get_recording_id(audio_path: Path, api_key: str) -> str | None:
    recording_id, _, _ = _acoustid_get_metadata(audio_path, api_key)
    return recording_id


def _mb_search_recording_ids(title: str, artist: str) -> list[str]:
    """Search MusicBrainz and return all candidate recording IDs ordered by score (>= 70)."""
    safe_title = title.replace('"', '').replace('\\', '')
    # Strip feat./ft./featuring from artist — MB stores only the primary artist name.
    main_artist, _ = _split_artist_featuring(artist)
    safe_artist = main_artist.replace('"', '').replace('\\', '')
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


def _mb_get_recording_data(recording_id: str) -> dict[str, object]:
    """Fetch genres, earliest release date, and featured artists for a MusicBrainz recording.

    Uses a single request with inc=tags+releases+artist-credits, then fetches
    release-group tags from the release-group IDs found inside the releases list.
    The old approach of browsing release-groups by recording ID (release-group?recording=...)
    is not supported by the MB API and returns HTTP 400.
    """
    rec_data = _mb_json_get(
        f"recording/{recording_id}",
        {"inc": "tags+releases+artist-credits"},
    )
    empty: dict[str, object] = {"genres": [], "release_date": None, "featured_artists": []}
    if not rec_data:
        return empty

    # ── Tags (recording-level) ────────────────────────────────────────────────
    recording_tags: list[dict] = rec_data.get("tags") or []
    logger.info("[MusicBrainz] Recording %s: %d recording-level tag(s)", recording_id, len(recording_tags))
    if recording_tags:
        logger.info(
            "[MusicBrainz] Recording tags: %s",
            [(t.get("name"), t.get("count")) for t in recording_tags],
        )

    # ── Releases → release-group IDs + earliest date ──────────────────────────
    releases: list[dict] = rec_data.get("releases") or []
    logger.info("[MusicBrainz] Recording %s: %d release(s)", recording_id, len(releases))
    seen_rg: set[str] = set()
    rg_ids: list[str] = []
    raw_dates: list[str] = []
    for rel in releases:
        date = rel.get("date")
        rg_id: str | None = (rel.get("release-group") or {}).get("id")
        rg_type: str = (rel.get("release-group") or {}).get("primary-type") or "?"
        logger.info(
            "[MusicBrainz]   Release: %r  date=%s  country=%s  status=%s  "
            "rg_type=%s  rg_id=%s",
            rel.get("title"), date, rel.get("country"), rel.get("status"),
            rg_type, rg_id,
        )
        if date:
            raw_dates.append(date)
        if rg_id and rg_id not in seen_rg:
            seen_rg.add(rg_id)
            rg_ids.append(rg_id)

    raw_dates.sort()
    earliest_date = _normalize_date(raw_dates[0]) if raw_dates else None
    if raw_dates:
        logger.info(
            "[MusicBrainz] Release dates found (%d): %s → earliest: %s",
            len(raw_dates), raw_dates, earliest_date,
        )

    # ── Artist credits → featured artists (all credited artists after the first) ──
    credits: list[object] = rec_data.get("artist-credit") or []
    featured_artists: list[str] = []
    for i, credit in enumerate(credits):
        if not isinstance(credit, dict):
            continue
        if i == 0:
            continue  # first entry is the main artist
        name: str = (credit.get("artist") or {}).get("name") or ""
        if name and name not in featured_artists:
            featured_artists.append(name)
    logger.info("[MusicBrainz] Featured artists from credits: %s", featured_artists)

    # ── Release-group tags (up to 2 groups to stay within rate limits) ────────
    rg_tags: list[dict] = []
    for rg_id in rg_ids[:2]:
        rg_data = _mb_json_get(f"release-group/{rg_id}", {"inc": "tags"})
        new_tags: list[dict] = (rg_data or {}).get("tags") or []
        logger.info("[MusicBrainz] Release-group %s: %d tag(s)", rg_id, len(new_tags))
        if new_tags:
            logger.info(
                "[MusicBrainz] Release-group tags: %s",
                [(t.get("name"), t.get("count")) for t in new_tags],
            )
        rg_tags.extend(new_tags)

    # ── Merge & deduplicate tags → genres ─────────────────────────────────────
    seen_tags: set[str] = set()
    merged: list[dict] = []
    for tag in recording_tags + rg_tags:
        name = (tag.get("name") or "").strip()
        if name and name not in seen_tags:
            seen_tags.add(name)
            merged.append(tag)

    genres: list[str] = [
        t["name"] for t in sorted(merged, key=lambda t: -int(t.get("count") or 0))
    ][:10]
    logger.info("[MusicBrainz] Genres for %s: %s", recording_id, genres)

    return {
        "genres": genres,
        "release_date": earliest_date,
        "featured_artists": featured_artists,
    }


def _mb_get_genres_for_recording(recording_id: str) -> list[str]:
    return list(_mb_get_recording_data(recording_id)["genres"])


_MB_EMPTY: dict[str, object] = {"genres": [], "release_date": None, "featured_artists": []}

_ALBUM_TYPE_RANK: dict[str, int] = {"album": 0, "single": 1, "ep": 2, "compilation": 3}


def _date_precision(d: str) -> int:
    """Return a precision score: 3=YYYY-MM-DD, 2=YYYY-MM, 1=YYYY, 0=empty."""
    if re.match(r'^\d{4}-\d{2}-\d{2}$', d):
        return 3
    if re.match(r'^\d{4}-\d{2}$', d):
        return 2
    if re.match(r'^\d{4}$', d):
        return 1
    return 0


def _better_date(current: str, candidate: str) -> str:
    """Return the preferred date: more precise wins; equal precision → earlier wins."""
    if not current:
        return candidate
    if not candidate:
        return current
    cp = _date_precision(current)
    kp = _date_precision(candidate)
    if kp > cp:
        return candidate
    if kp < cp:
        return current
    return candidate if candidate < current else current


def _accumulate_mb_partial(base: dict[str, object], update: dict[str, object]) -> None:
    """Merge update into base in-place: best release_date, combined artists, first genres found."""
    update_date = str(update.get("release_date") or "")
    base_date = str(base.get("release_date") or "")
    if update_date:
        best = _better_date(base_date, update_date)
        base["release_date"] = best

    all_fa: list[str] = list(base.get("featured_artists") or [])
    for fa in (update.get("featured_artists") or []):
        if fa not in all_fa:
            all_fa.append(fa)
    base["featured_artists"] = all_fa

    if not base.get("genres") and update.get("genres"):
        base["genres"] = list(update["genres"])


def _fetch_musicbrainz_data(
    audio_path: Path,
    acoustid_api_key: str,
    title: str = "",
    artist: str = "",
    lastfm_mbid: str = "",
    prefetched_recording_id: str | None = None,
    acoustid_done: bool = False,
) -> dict[str, object]:
    """Resolve genres, earliest release date, and featured artists from MusicBrainz.

    Priority:
    1. Last.fm MBID  — most reliable starting point
    2. AcoustID recording ID (prefetched or freshly fingerprinted)
    3. JSON text search — iterates through all score >= 70 candidates
    """
    try:
        import musicbrainzngs
    except ImportError:
        logger.warning("[MusicBrainz] musicbrainzngs not installed — skipping")
        return dict(_MB_EMPTY)

    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
    musicbrainzngs.set_useragent(*_MB_USERAGENT)

    partial: dict[str, object] = dict(_MB_EMPTY)

    # Step 1 — Last.fm MBID
    if lastfm_mbid:
        logger.info("[MusicBrainz] Trying Last.fm MBID: %s", lastfm_mbid)
        data = _mb_get_recording_data(lastfm_mbid)
        _accumulate_mb_partial(partial, data)
        if data["genres"]:
            logger.info("[MusicBrainz] Genres via Last.fm MBID: %s", data["genres"])
            return partial
        logger.warning("[MusicBrainz] Last.fm MBID yielded no genres — continuing to next source")

    # Step 2 — AcoustID recording ID
    acoustid_recording_id = prefetched_recording_id
    if acoustid_recording_id:
        logger.info("[MusicBrainz] Using prefetched AcoustID recording_id: %s", acoustid_recording_id)
    elif acoustid_done:
        logger.info("[MusicBrainz] AcoustID already ran — no recording_id found, skipping re-fingerprint")
    elif acoustid_api_key:
        acoustid_recording_id = _acoustid_get_recording_id(audio_path, acoustid_api_key)
    else:
        logger.info("[MusicBrainz] No ACOUSTID_API_KEY — skipping fingerprint")

    if acoustid_recording_id:
        data = _mb_get_recording_data(acoustid_recording_id)
        _accumulate_mb_partial(partial, data)
        if data["genres"]:
            logger.info("[MusicBrainz] Genres via AcoustID recording: %s", data["genres"])
            return partial
        logger.warning("[MusicBrainz] AcoustID recording has no genre tags — continuing to text search")

    # Step 3 — JSON text search: always run when genres are still empty
    if not title or not artist:
        logger.warning("[MusicBrainz] Cannot text-search — title or artist missing")
        return partial

    recording_ids = _mb_search_recording_ids(title, artist)
    for i, recording_id in enumerate(recording_ids):
        logger.info("[MusicBrainz] Trying text-search candidate %d/%d: %s", i + 1, len(recording_ids), recording_id)
        data = _mb_get_recording_data(recording_id)
        _accumulate_mb_partial(partial, data)
        if data["genres"]:
            logger.info("[MusicBrainz] Genres via text-search candidate %d: %s", i + 1, data["genres"])
            return partial

    logger.warning("[MusicBrainz] No genres found across all candidates for %r / %r", artist, title)
    return partial


# ── Main entry point ──────────────────────────────────────────────────────────

def extract_all_metadata(
    audio_path: Path,
    lastfm_api_key: str = "",
    acoustid_api_key: str = "",
    spotify_client_id: str = "",
    spotify_client_secret: str = "",
) -> dict[str, object]:
    # ── File-level technical metadata (duration, bitrate, etc.) ──────────────
    file_meta = extract_file_metadata(audio_path)
    result = dict(file_meta)
    # Title/artist from embedded tags are not used — AcoustID is the only source of truth
    result.pop("title", None)
    result.pop("artist", None)

    # ── AcoustID fingerprint — mandatory gate ─────────────────────────────────
    if not acoustid_api_key:
        logger.warning("[AcoustID] No API key — cannot verify song identity, skipping %s", audio_path.name)
        return {}

    acoustid_recording_id, aid_title, aid_artist = _acoustid_get_metadata(audio_path, acoustid_api_key)

    if not aid_title and not aid_artist:
        logger.warning("[Metadata] No AcoustID match for %s — skipping", audio_path.name)
        return {}

    # Split "David Guetta feat. Kid Cudi" → artist + featured artists
    raw_aid_artist = aid_artist or ""
    artist, aid_feat = _split_artist_featuring(raw_aid_artist)
    title = aid_title or ""

    result["title"] = title
    result["artist"] = artist
    if aid_feat:
        result["featured_artists"] = list(aid_feat)

    logger.info("[AcoustID] title=%r  artist=%r  recording_id=%s", title, artist, acoustid_recording_id)

    # ── Last.fm ───────────────────────────────────────────────────────────────
    track_info: dict[str, object] | None = None
    artist_info: dict[str, object] = {}
    similar = None

    if not lastfm_api_key:
        logger.info("[Last.fm] Skipped — no LASTFM_API_KEY")
    elif not title or not artist:
        logger.info("[Last.fm] Skipped — title or artist missing")
    else:
        logger.info("[Last.fm] Fetching: %r — %r", artist, title)
        track_info = _fetch_track_info(title, artist, lastfm_api_key)
        if track_info:
            artist_name = str(track_info.get("artist") or artist)
            artist_info = _fetch_artist_info(artist_name, lastfm_api_key) or {}
            similar = _fetch_similar_tracks(title, artist_name, lastfm_api_key)

            existing_featured: list[str] = list(result.get("featured_artists") or [])
            for fa in (track_info.get("featured_artists") or []):
                if fa not in existing_featured:
                    existing_featured.append(fa)
            result["featured_artists"] = existing_featured

    mb_title = str(result.get("title") or title)
    mb_artist = str(result.get("artist") or artist)
    lastfm_mbid = str(track_info.get("mbid") or "") if track_info else ""
    if lastfm_mbid:
        logger.info("[Metadata] Last.fm MBID: %s", lastfm_mbid)
    else:
        logger.info("[Metadata] No Last.fm MBID — will use AcoustID recording_id or text search")

    # ── Spotify (album + release_date) ────────────────────────────────────────
    if not spotify_client_id or not spotify_client_secret:
        logger.info("[Spotify] Skipped — no credentials")
    elif not mb_title or not mb_artist:
        logger.info("[Spotify] Skipped — title or artist missing")
    else:
        logger.info("[Spotify] Fetching: %r — %r", mb_artist, mb_title)
        token = _spotify_get_token(spotify_client_id, spotify_client_secret)
        if token:
            spotify_info = _fetch_spotify_info(mb_title, mb_artist, token)
            if not spotify_info and raw_aid_artist and raw_aid_artist != mb_artist:
                # Try with full credit string (e.g. "David Guetta feat. Kid Cudi") in case Spotify needs it
                spotify_info = _fetch_spotify_info(mb_title, raw_aid_artist, token)

            if spotify_info:
                if spotify_info.get("album"):
                    result["album"] = spotify_info["album"]
                    logger.info("[Spotify] album: %s", result["album"])
                if spotify_info.get("release_date") and not result.get("release_date"):
                    result["release_date"] = spotify_info["release_date"]
                    logger.info("[Spotify] release_date: %s", result["release_date"])
                for fa in (spotify_info.get("featured_artists") or []):
                    existing_fa: list[str] = list(result.get("featured_artists") or [])
                    if fa not in existing_fa:
                        existing_fa.append(fa)
                        result["featured_artists"] = existing_fa
                        logger.info("[Spotify] Featured artist added: %s", fa)
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

    # ── MusicBrainz (genres + earliest release date + featured artists) ───────
    mb_data = _fetch_musicbrainz_data(
        audio_path, acoustid_api_key,
        title=mb_title, artist=mb_artist,
        lastfm_mbid=lastfm_mbid,
        prefetched_recording_id=acoustid_recording_id,
        acoustid_done=True,
    )
    result["genres"] = mb_data["genres"]
    result.setdefault("album_mbid", None)

    # Merge featured artists: file tag → Last.fm → Spotify → MusicBrainz, then deduplicate
    all_featured: list[str] = list(result.get("featured_artists") or [])
    for fa in (mb_data.get("featured_artists") or []):
        if fa not in all_featured:
            all_featured.append(fa)
    all_featured = _dedup_featured_artists(all_featured)
    if all_featured:
        result["featured_artists"] = all_featured
        logger.info("[Metadata] Featured artists: %s", all_featured)

    # Use the best release date across Spotify and MusicBrainz (more precise and/or earlier wins)
    mb_release_date: str | None = mb_data.get("release_date")  # type: ignore[assignment]
    if mb_release_date:
        current_date = str(result.get("release_date") or "")
        best_date = _better_date(current_date, mb_release_date)
        if best_date != current_date:
            result["release_date"] = best_date
            logger.info(
                "[MusicBrainz] Better release date found: %s (was: %s)",
                best_date, current_date or "none",
            )
        else:
            logger.info(
                "[MusicBrainz] Release date not improved: MB=%s, keeping Spotify=%s",
                mb_release_date, current_date,
            )

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

    # ── AcoustID title/artist are the source of truth — restore if changed ───────
    _has_parens = bool(re.search(r'\(', title))
    final_title = str(result.get("title") or title)
    if final_title != title:
        if not _has_parens and re.search(r'\(', final_title):
            logger.warning(
                "[Metadata] Title gained parenthetical content from downstream source "
                "(%r → %r) — restoring AcoustID title",
                final_title, title,
            )
            result["title"] = title
        elif final_title != title:
            logger.warning(
                "[Metadata] Title was changed by downstream source (%r → %r) — restoring AcoustID title",
                final_title, title,
            )
            result["title"] = title
    result["artist"] = artist

    # ── Summary ───────────────────────────────────────────────────────────────
    _TRACKED = ("title", "artist", "album", "release_date", "genres", "album_mbid")
    found = [f for f in _TRACKED if result.get(f)]
    missing = [f for f in _TRACKED if not result.get(f)]
    logger.info("[Metadata] Summary — found: %s", found)
    if missing:
        logger.warning("[Metadata] Summary — NOT found: %s", missing)

    return result
