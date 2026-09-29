"""MusicBrainz web-service client: genres, earliest release date, featured artists."""
import json
import logging
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from src.metadata.acoustid_client import get_recording_id
from src.metadata.cleaning import (
    better_date,
    normalize_date,
    SAMPLER_NAME_RE,
    plain_quotes,
    split_artist_featuring,
    strip_version_markers,
)

logger = logging.getLogger(__name__)

_MB_USERAGENT = ("MusicRecommender", "0.1", "user@example.com")
_mb_last_json_ts: float = 0.0

_MB_EMPTY: dict[str, object] = {
    "genres": [], "release_date": None, "featured_artists": [], "album_mbid": None, "album": None,
}

# Release-group types in order of preference for "the album this song is on".
_ALBUM_TYPE_RANK: dict[str, int] = {"Album": 0, "EP": 1, "Single": 2}
_UNDATED = "9999"
# A film's soundtrack is where its songs first appeared; every other secondary type is not the album.
_ALBUM_SECONDARY_TYPES = frozenset({"Soundtrack"})
# An album that first came out more than this long after the song is a later collection.
_ALBUM_WINDOW_YEARS = 1

# Only for building the search query: the first name of "A, B", "A & B", "A x B".
_FIRST_ARTIST_RE = re.compile(r",\s*|\s+&\s+|\s+x\s+|\s+and\s+|\s+(?:feat\.?|ft\.?|featuring)\s+", re.IGNORECASE)

# MusicBrainz answers 503 when more than ~1 request/second arrives from one IP.
_MB_ATTEMPTS = 3
_MB_MIN_INTERVAL_SECONDS = 1.1
_MB_REQUEST_LOCK = threading.Lock()
_MB_BUSY_CODES = (429, 503)
_MB_BUSY_BACKOFF_SECONDS = 3


@dataclass(frozen=True)
class RecordingIdentity:
    """Title and credited artists of a MusicBrainz recording."""

    title: str
    artist: str
    featured_artists: list[str] = field(default_factory=list)


def _is_latin(text: str) -> bool:
    return all(unicodedata.name(ch, "").startswith("LATIN") for ch in text if ch.isalpha())


def _credit_name(credit: dict) -> str:
    """Artist name of one credit; a person written in another script gets the Latin sort name.

    MusicBrainz names Tchaikovsky "Пётр Ильич Чайковский" but sorts him as
    "Tchaikovsky, Pyotr Ilyich" → "Pyotr Ilyich Tchaikovsky".
    """
    artist = credit.get("artist") or {}
    name = str(artist.get("name") or credit.get("name") or "")
    family, comma, given = str(artist.get("sort-name") or "").partition(",")
    if name and not _is_latin(name) and comma and _is_latin(family + given):
        return f"{given.strip()} {family.strip()}".strip()
    return name


def recording_identity(rec_data: dict) -> RecordingIdentity | None:
    """Read title, main artist and featured artists from a recording with ``artist-credits``.

    The first credit is the main artist, every further one is featured.
    Returns None when the recording lacks a title or an artist.
    """
    names = [_credit_name(c) for c in rec_data.get("artist-credit") or [] if isinstance(c, dict)]
    names = [plain_quotes(n) for n in names if n]
    title = str(rec_data.get("title") or "")
    if not title or not names:
        return None
    return RecordingIdentity(
        title=plain_quotes(strip_version_markers(title)), artist=names[0], featured_artists=names[1:]
    )


def _comparable(text: str) -> str:
    """Case-, accent- and punctuation-insensitive form for comparing names."""
    decomposed = unicodedata.normalize("NFKD", strip_version_markers(text).casefold())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w]", " ", plain).split())


def _has_surname(rec: dict, surname: str) -> bool:
    """True when the recording's main artist is a person sorted under ``surname`` ("Beethoven, Ludwig van")."""
    credits = rec.get("artist-credit") or []
    sort_name = str(((credits[0] if credits else {}).get("artist") or {}).get("sort-name") or "")
    family, comma, _ = sort_name.partition(",")
    return bool(comma) and bool(surname) and _comparable(family) == surname


def _is_by(rec: dict, wanted_artist: str) -> bool:
    """True when the recording's main artist is ``wanted_artist`` (already :func:`_comparable`).

    Accepts the same artist, the first of several ("Lady Gaga" for "Lady Gaga,
    Bradley Cooper"), or a person of that surname ("Beethoven" → "Ludwig van
    Beethoven", not the band "Electric Beethoven").
    """
    identity = recording_identity(rec)
    main = _comparable(identity.artist) if identity else ""
    return bool(main) and (
        wanted_artist == main or wanted_artist.startswith(main + " ") or _has_surname(rec, wanted_artist)
    )


def canonical_from_search(search_data: dict, title: str, artist: str) -> RecordingIdentity | None:
    """The MusicBrainz spelling of a song named by a video title or the uploader.

    A recording counts when its title matches ``title`` and its main artist is
    ``artist`` or the start of it ("Lady Gaga" for "Lady Gaga, Bradley Cooper");
    band names like "Earth, Wind & Fire" therefore stay whole. Returns None
    when no recording fits, e.g. a performer credited for a composer's piece.
    """
    wanted_title, wanted_artist = _comparable(title), _comparable(artist)
    matches: list[RecordingIdentity] = []
    for rec in search_data.get("recordings") or []:
        identity = recording_identity(rec)
        if identity is None or _comparable(identity.title) != wanted_title:
            continue
        if _is_by(rec, wanted_artist):
            matches.append(identity)
    # "Gymnopédie" over "Gymnopedie" when the video spells it that way.
    wanted = strip_version_markers(title)
    same_case = [m for m in matches if m.title == wanted]
    same_letters = [m for m in matches if m.title.casefold() == wanted.casefold()]
    return (same_case or same_letters or matches or [None])[0]


def fetch_canonical_recording(title: str, artist: str) -> RecordingIdentity | None:
    """Look up how MusicBrainz spells a song that AcoustID did not recognise; None if unknown."""
    first_artist = _FIRST_ARTIST_RE.split(artist, maxsplit=1)[0]
    safe_title = strip_version_markers(title).replace('"', "").replace("\\", "")
    safe_artist = first_artist.replace('"', "").replace("\\", "")
    data = _mb_json_get("recording", {"query": f'recording:"{safe_title}" AND artist:"{safe_artist}"', "limit": "25"})
    identity = canonical_from_search(data or {}, title, artist)
    logger.info("[MusicBrainz] Canonical name for %r / %r: %s", artist, title, identity)
    return identity


def fetch_recording_identity(recording_id: str) -> RecordingIdentity | None:
    """Look up a recording's title and credited artists on MusicBrainz; None if unreachable or incomplete."""
    rec_data = _mb_json_get(f"recording/{recording_id}", {"inc": "artist-credits"})
    return recording_identity(rec_data) if rec_data else None


# Recordings on at least one official album.
_ALBUM_FILTER = " AND status:official AND primarytype:album"
# Popular songs have hundreds of live recordings that crowd the studio album out of the first
# results page. This narrower query drops every recording that appears on any live album or
# compilation — including many studio recordings — so it only supplements the broad one.
_NARROW_ALBUM_FILTER = _ALBUM_FILTER + " AND NOT secondarytype:live AND NOT secondarytype:compilation"
_ALBUM_SEARCH_LIMIT = 100
# Candidate groups (most frequent first) whose real first release date is looked up.
_FIRST_RELEASE_LOOKUPS = 4


def _released_by(release: dict, artist: str) -> bool:
    """True when the release's first credited artist is ``artist``; releases without own credit inherit the recording's."""
    credits = release.get("artist-credit") or []
    if not credits:
        return True
    name = str((credits[0].get("artist") or {}).get("name") or credits[0].get("name") or "")
    return name.casefold() == artist.casefold()


def _same_song_title(a: str, b: str) -> bool:
    return strip_version_markers(a).casefold() == strip_version_markers(b).casefold()


def _song_album_candidates(
    search_data: dict, title: str, artist: str, allow_soundtracks: bool = True
) -> "list[_AlbumCandidate]":
    """Album candidates from search hits with the same title by the same main artist, on that artist's releases."""
    candidates: list[_AlbumCandidate] = []
    for rec in search_data.get("recordings") or []:
        credits = rec.get("artist-credit") or []
        main = str(((credits[0] if credits else {}).get("artist") or {}).get("name") or "")
        if _same_song_title(str(rec.get("title") or ""), title) and main.casefold() == artist.casefold():
            candidates.extend(
                c for c in (
                    _album_candidate(rel, allow_soundtracks)
                    for rel in rec.get("releases") or [] if _released_by(rel, artist)
                )
                if c is not None
            )
    return candidates


def album_from_search(
    search_data: dict,
    title: str,
    artist: str,
    min_releases: int = 1,
    first_release: dict[str, str] | None = None,
    allow_soundtracks: bool = True,
) -> tuple[str | None, str | None]:
    """Album of a song across all its recordings in a MusicBrainz recording search.

    Only hits with the same title (ignoring edit/remaster markers) by the same
    main artist count, and only releases credited to that artist — samplers
    ("Various Artists") and a guest's own albums do not. Among their official
    studio albums (see :func:`pick_album`), the one the song was released on
    most often wins — reissues and country editions pile up on the real album,
    while a one-off appearance on some other record does not. The type order
    and the song's own single come first, as in :func:`pick_album`.

    ``min_releases`` drops groups the song appears on fewer times — for songs
    identified only by name, where a single sampler hit is likely a stranger.
    ``first_release`` maps group ids to their first release date; search hits
    list only some releases per recording, so without it an album whose
    original pressing is missing looks like a later reissue.
    """
    candidates = _near_debut(_song_album_candidates(search_data, title, artist, allow_soundtracks), first_release)
    counts = Counter(c.group_id for c in candidates)
    candidates = [c for c in candidates if counts[c.group_id] >= min_releases]
    if not candidates:
        return None, None
    best = min(candidates, key=lambda c: (c.rank, _not_own_title(c, title), -counts[c.group_id], c.date))
    return best.group_id, best.title or None


def fetch_song_album(
    title: str, artist: str, min_releases: int = 1, allow_soundtracks: bool = True
) -> tuple[str | None, str | None]:
    """``(release_group_id, album)`` of the song's studio album, searched by title and artist.

    When the broad search has more hits than one page holds, the narrow one
    is added; each recording counts once. The most frequent candidate groups
    get their real first release date looked up.
    """
    safe_title = strip_version_markers(title).replace('"', "").replace("\\", "")
    safe_artist = artist.replace('"', "").replace("\\", "")
    base = f'recording:"{safe_title}" AND artist:"{safe_artist}"'

    def search(album_filter: str) -> dict:
        return _mb_json_get("recording", {"query": base + album_filter, "limit": str(_ALBUM_SEARCH_LIMIT)}) or {}

    broad = search(_ALBUM_FILTER)
    recordings: list[dict] = list(broad.get("recordings") or [])
    if int(broad.get("count") or 0) > len(recordings):
        seen = {r.get("id") for r in recordings}
        recordings += [r for r in search(_NARROW_ALBUM_FILTER).get("recordings") or [] if r.get("id") not in seen]
    search_data = {"recordings": recordings}

    counts = Counter(c.group_id for c in _song_album_candidates(search_data, title, artist, allow_soundtracks))
    first_release = {
        group_id: date for group_id, _ in counts.most_common(_FIRST_RELEASE_LOOKUPS)
        if (date := _group_first_release(group_id))
    }
    album = album_from_search(search_data, title, artist, min_releases, first_release, allow_soundtracks)
    logger.info("[MusicBrainz] Song album for %r / %r: %s", artist, title, album)
    return album


def _group_first_release(group_id: str) -> str | None:
    data = _mb_json_get(f"release-group/{group_id}", {}) or {}
    return str(data.get("first-release-date") or "") or None


def performed_work_ids(rec_data: dict) -> list[str]:
    """Ids of the works (compositions) a recording with ``work-rels`` is a performance of."""
    return [
        r["work"]["id"] for r in rec_data.get("relations") or []
        if r.get("target-type") == "work" and r.get("type") == "performance" and (r.get("work") or {}).get("id")
    ]


def work_composers(work_data: dict) -> list[str]:
    """Composer names of a work fetched with ``artist-rels``."""
    return [
        _credit_name({"artist": r["artist"]}) for r in work_data.get("relations") or []
        if r.get("target-type") == "artist" and r.get("type") == "composer" and (r.get("artist") or {}).get("name")
    ]


def fetch_recording_composers(recording_id: str) -> list[str]:
    """Composers of the works a recording performs; empty if MusicBrainz knows none or is unreachable."""
    rec_data = _mb_json_get(f"recording/{recording_id}", {"inc": "work-rels"})
    composers: list[str] = []
    for work_id in performed_work_ids(rec_data or {}):
        for name in work_composers(_mb_json_get(f"work/{work_id}", {"inc": "artist-rels"}) or {}):
            if name not in composers:
                composers.append(name)
    logger.info("[MusicBrainz] Composers of %s: %s", recording_id, composers)
    return composers


@dataclass(frozen=True)
class _AlbumCandidate:
    rank: int
    date: str
    group_id: str
    title: str


def _album_candidate(release: dict, allow_soundtracks: bool = True) -> _AlbumCandidate | None:
    """The release's group if it can be "the album": official, album/EP/single, no live/compilation/etc."""
    group = release.get("release-group") or {}
    rank = _ALBUM_TYPE_RANK.get(group.get("primary-type") or "")
    if release.get("status") != "Official" or rank is None or not group.get("id"):
        return None
    allowed = _ALBUM_SECONDARY_TYPES if allow_soundtracks else frozenset()
    if set(group.get("secondary-types") or []) - allowed:
        return None
    title = str(group.get("title") or release.get("title") or "")
    if SAMPLER_NAME_RE.search(title):
        return None
    return _AlbumCandidate(rank, str(release.get("date") or _UNDATED), group["id"], title)


def _year(date: str) -> int | None:
    return int(date[:4]) if date[:4].isdigit() and date != _UNDATED else None


def _near_debut(
    candidates: list[_AlbumCandidate], first_release: dict[str, str] | None = None
) -> list[_AlbumCandidate]:
    """Keep releases whose group first came out within a year of the song's first release.

    A song's album comes out around the song; best-ofs, games and samplers
    years later ("96 Months", "DJ Hero") do not. Undated groups only count
    when nothing is dated.
    """
    first_year: dict[str, int] = {}
    for c in candidates:
        year = _year(c.date)
        if year is not None:
            first_year[c.group_id] = min(first_year.get(c.group_id, year), year)
    for group_id, date in (first_release or {}).items():
        year = _year(date)
        if year is not None and group_id in first_year:
            first_year[group_id] = year
    if not first_year:
        return candidates
    debut = min(first_year.values())
    return [
        c for c in candidates
        if c.group_id in first_year and first_year[c.group_id] - debut <= _ALBUM_WINDOW_YEARS
    ]


def _not_own_title(candidate: _AlbumCandidate, song_title: str | None) -> int:
    """0 when the release is named after the song (its own single), else 1."""
    return 0 if song_title and _same_song_title(candidate.title, song_title) else 1


def pick_album(releases: list[dict], song_title: str | None = None) -> tuple[str | None, str | None]:
    """Return ``(release_group_id, title)`` of the album a recording first appeared on.

    Official releases only; live albums, compilations and the like are
    skipped (soundtracks count), and so is anything that first came out more
    than a year after the song. An album beats an EP beats a single; within a
    type the song's own single (named like ``song_title``) wins, then the
    earliest release (a reissue never beats the original).
    """
    candidates = _near_debut([c for c in map(_album_candidate, releases) if c is not None])
    if not candidates:
        return None, None
    best = min(candidates, key=lambda c: (c.rank, _not_own_title(c, song_title), c.date))
    return best.group_id, best.title or None


def _mb_json_get(path: str, params: dict[str, str]) -> dict | None:
    """
    Rate-limited direct JSON request to MusicBrainz web service.
    Respects the 1 request/second limit independently of musicbrainzngs calls.
    A busy server (503/429) is asked again after a pause; None only when every
    attempt failed.
    """
    query = urllib.parse.urlencode({**params, "fmt": "json"})
    url = f"https://musicbrainz.org/ws/2/{path}?{query}"
    ua = f"{_MB_USERAGENT[0]}/{_MB_USERAGENT[1]} ( {_MB_USERAGENT[2]} )"
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json"})

    for attempt in range(1, _MB_ATTEMPTS + 1):
        try:
            return _mb_send(req)
        except urllib.error.HTTPError as exc:
            if exc.code not in _MB_BUSY_CODES or attempt == _MB_ATTEMPTS:
                logger.warning("[MusicBrainz] JSON API failed (HTTP %s) for %s", exc.code, path)
                return None
            pause = _MB_BUSY_BACKOFF_SECONDS * attempt
            logger.info("[MusicBrainz] Busy (HTTP %s) — retrying %s in %ds", exc.code, path, pause)
            time.sleep(pause)
        except Exception as exc:
            logger.warning("[MusicBrainz] JSON API failed (%s): %s", type(exc).__name__, exc)
            return None
    return None


def _mb_send(req: urllib.request.Request) -> dict:
    """One request, at most one at a time and ``_MB_MIN_INTERVAL_SECONDS`` apart across all threads.

    Several songs are identified in parallel; MusicBrainz answers 503 to
    more than about one request per second from the same address.
    """
    global _mb_last_json_ts
    with _MB_REQUEST_LOCK:
        wait = _MB_MIN_INTERVAL_SECONDS - (time.time() - _mb_last_json_ts)
        if wait > 0:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        finally:
            _mb_last_json_ts = time.time()


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

    wanted_artist = _comparable(main_artist)
    candidates = [r for r in recordings if int(r.get("score", 0)) >= 70 and _is_by(r, wanted_artist)]
    if not candidates:
        logger.warning("[MusicBrainz] No result by %r with score >= 70", main_artist)
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

    Uses a single request with inc=tags+releases+release-groups+artist-credits, then fetches
    release-group tags from the release-group IDs found inside the releases list.
    The old approach of browsing release-groups by recording ID (release-group?recording=...)
    is not supported by the MB API and returns HTTP 400.
    """
    rec_data = _mb_json_get(
        f"recording/{recording_id}",
        {"inc": "tags+releases+release-groups+artist-credits"},
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

    main_credit = recording_identity(rec_data)
    own_releases = [r for r in releases if main_credit is None or _released_by(r, main_credit.artist)]
    album_mbid, album = pick_album(own_releases, main_credit.title if main_credit else None)
    logger.info("[MusicBrainz] Album for %s: %r (%s)", recording_id, album, album_mbid)

    return {
        "genres": genres,
        "release_date": earliest_date,
        "featured_artists": featured_artists,
        "album_mbid": album_mbid,
        "album": album,
    }


def _accumulate_partial(base: dict[str, object], update: dict[str, object], identified: bool) -> None:
    """Merge update into base in-place: best release_date, first genres found.

    Featured artists are credits of one specific recording, so they are taken
    only from the ``identified`` one (the first looked up); further candidates
    only fill genres and dates.
    """
    update_date = str(update.get("release_date") or "")
    base_date = str(base.get("release_date") or "")
    if update_date:
        best = better_date(base_date, update_date)
        base["release_date"] = best

    if identified:
        base["featured_artists"] = list(update.get("featured_artists") or [])

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
    1. AcoustID recording ID (prefetched or freshly fingerprinted) — the audio itself
    2. Last.fm MBID
    3. JSON text search — iterates through all score >= 70 candidates

    Featured artists come only from the first recording looked up.
    """
    try:
        import musicbrainzngs
    except ImportError:
        logger.warning("[MusicBrainz] musicbrainzngs not installed — skipping")
        return dict(_MB_EMPTY)

    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
    musicbrainzngs.set_useragent(*_MB_USERAGENT)

    partial: dict[str, object] = dict(_MB_EMPTY)
    looked_up = 0  # the first recording looked up is the identified one (featured artists)

    # Step 1 — AcoustID recording ID: the fingerprinted recording itself
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
        _accumulate_partial(partial, data, identified=looked_up == 0)
        looked_up += 1
        if data["genres"]:
            logger.info("[MusicBrainz] Genres via AcoustID recording: %s", data["genres"])
            return partial
        logger.warning("[MusicBrainz] AcoustID recording has no genre tags — continuing")

    # Step 2 — Last.fm MBID
    if lastfm_mbid and lastfm_mbid != acoustid_recording_id:
        logger.info("[MusicBrainz] Trying Last.fm MBID: %s", lastfm_mbid)
        data = _get_recording_data(lastfm_mbid)
        _accumulate_partial(partial, data, identified=looked_up == 0)
        looked_up += 1
        if data["genres"]:
            logger.info("[MusicBrainz] Genres via Last.fm MBID: %s", data["genres"])
            return partial
        logger.warning("[MusicBrainz] Last.fm MBID yielded no genres — continuing to text search")

    # Step 3 — JSON text search: always run when genres are still empty
    if not title or not artist:
        logger.warning("[MusicBrainz] Cannot text-search — title or artist missing")
        return partial

    recording_ids = _search_recording_ids(title, artist)
    for i, recording_id in enumerate(recording_ids):
        logger.info("[MusicBrainz] Trying text-search candidate %d/%d: %s", i + 1, len(recording_ids), recording_id)
        data = _get_recording_data(recording_id)
        _accumulate_partial(partial, data, identified=looked_up == 0)
        looked_up += 1
        if data["genres"]:
            logger.info("[MusicBrainz] Genres via text-search candidate %d: %s", i + 1, data["genres"])
            return partial

    logger.warning("[MusicBrainz] No genres found across all candidates for %r / %r", artist, title)
    return partial
