"""MusicBrainz web-service client: genres, earliest release date, featured artists."""
import json
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from src.metadata.acoustid_client import get_recording_id
from src.metadata.cleaning import better_date, normalize_date, split_artist_featuring

logger = logging.getLogger(__name__)

_MB_USERAGENT = ("MusicRecommender", "0.1", "user@example.com")
_mb_last_json_ts: float = 0.0

_MB_EMPTY: dict[str, object] = {
    "genres": [], "release_date": None, "featured_artists": [], "album_mbid": None, "album": None,
}

# Release-group types in order of preference for "the album this song is on".
_ALBUM_TYPE_RANK: dict[str, int] = {"Album": 0, "EP": 1, "Single": 2}
_UNDATED = "9999"


@dataclass(frozen=True)
class RecordingIdentity:
    """Title and credited artists of a MusicBrainz recording."""

    title: str
    artist: str
    featured_artists: list[str] = field(default_factory=list)


def recording_identity(rec_data: dict) -> RecordingIdentity | None:
    """Read title, main artist and featured artists from a recording with ``artist-credits``.

    The first credit is the main artist, every further one is featured.
    Returns None when the recording lacks a title or an artist.
    """
    names = [
        str((c.get("artist") or {}).get("name") or c.get("name") or "")
        for c in rec_data.get("artist-credit") or [] if isinstance(c, dict)
    ]
    names = [n for n in names if n]
    title = str(rec_data.get("title") or "")
    if not title or not names:
        return None
    return RecordingIdentity(title=title, artist=names[0], featured_artists=names[1:])


def fetch_recording_identity(recording_id: str) -> RecordingIdentity | None:
    """Look up a recording's title and credited artists on MusicBrainz; None if unreachable or incomplete."""
    rec_data = _mb_json_get(f"recording/{recording_id}", {"inc": "artist-credits"})
    return recording_identity(rec_data) if rec_data else None


def pick_album(releases: list[dict]) -> tuple[str | None, str | None]:
    """Return ``(release_group_id, title)`` of the album a recording first appeared on.

    Official releases only; an album beats an EP beats a single, and within
    a type the earliest release wins (a reissue never beats the original).
    """
    candidates: list[tuple[int, str, str, str]] = []
    for rel in releases:
        group = rel.get("release-group") or {}
        rank = _ALBUM_TYPE_RANK.get(group.get("primary-type") or "")
        if rel.get("status") != "Official" or rank is None or not group.get("id"):
            continue
        title = group.get("title") or rel.get("title") or ""
        candidates.append((rank, rel.get("date") or _UNDATED, group["id"], title))
    if not candidates:
        return None, None
    _, _, group_id, title = min(candidates)
    return group_id, title or None


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


def _search_recording_ids(title: str, artist: str) -> list[str]:
    """Search MusicBrainz and return all candidate recording IDs ordered by score (>= 70)."""
    safe_title = title.replace('"', '').replace('\\', '')
    # Strip feat./ft./featuring from artist — MB stores only the primary artist name.
    main_artist, _ = split_artist_featuring(artist)
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


def _get_recording_data(recording_id: str) -> dict[str, object]:
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
    if not rec_data:
        return dict(_MB_EMPTY)

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
    earliest_date = normalize_date(raw_dates[0]) if raw_dates else None
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

    album_mbid, album = pick_album(releases)
    logger.info("[MusicBrainz] Album for %s: %r (%s)", recording_id, album, album_mbid)

    return {
        "genres": genres,
        "release_date": earliest_date,
        "featured_artists": featured_artists,
        "album_mbid": album_mbid,
        "album": album,
    }


def _accumulate_partial(base: dict[str, object], update: dict[str, object]) -> None:
    """Merge update into base in-place: best release_date, combined artists, first genres found."""
    update_date = str(update.get("release_date") or "")
    base_date = str(base.get("release_date") or "")
    if update_date:
        best = better_date(base_date, update_date)
        base["release_date"] = best

    all_fa: list[str] = list(base.get("featured_artists") or [])
    for fa in (update.get("featured_artists") or []):
        if fa not in all_fa:
            all_fa.append(fa)
    base["featured_artists"] = all_fa

    if not base.get("genres") and update.get("genres"):
        base["genres"] = list(update["genres"])

    if not base.get("album_mbid") and update.get("album_mbid"):
        base["album_mbid"] = update["album_mbid"]
        base["album"] = update.get("album")


def fetch_musicbrainz_data(
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
        data = _get_recording_data(lastfm_mbid)
        _accumulate_partial(partial, data)
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
        acoustid_recording_id = get_recording_id(audio_path, acoustid_api_key)
    else:
        logger.info("[MusicBrainz] No ACOUSTID_API_KEY — skipping fingerprint")

    if acoustid_recording_id:
        data = _get_recording_data(acoustid_recording_id)
        _accumulate_partial(partial, data)
        if data["genres"]:
            logger.info("[MusicBrainz] Genres via AcoustID recording: %s", data["genres"])
            return partial
        logger.warning("[MusicBrainz] AcoustID recording has no genre tags — continuing to text search")

    # Step 3 — JSON text search: always run when genres are still empty
    if not title or not artist:
        logger.warning("[MusicBrainz] Cannot text-search — title or artist missing")
        return partial

    recording_ids = _search_recording_ids(title, artist)
    for i, recording_id in enumerate(recording_ids):
        logger.info("[MusicBrainz] Trying text-search candidate %d/%d: %s", i + 1, len(recording_ids), recording_id)
        data = _get_recording_data(recording_id)
        _accumulate_partial(partial, data)
        if data["genres"]:
            logger.info("[MusicBrainz] Genres via text-search candidate %d: %s", i + 1, data["genres"])
            return partial

    logger.warning("[MusicBrainz] No genres found across all candidates for %r / %r", artist, title)
    return partial
