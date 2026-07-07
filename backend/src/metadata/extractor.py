"""Orchestrates all metadata providers into one result dict.

Flow: file tags → AcoustID (mandatory identity gate) → Last.fm → Spotify →
MusicBrainz. AcoustID title/artist are the source of truth; downstream
sources only enrich (album, dates, genres, featured artists, stats).
"""
import logging
import re
from pathlib import Path

from src.metadata.acoustid_client import get_acoustid_metadata
from src.metadata.cleaning import better_date, dedup_featured_artists, split_artist_featuring
from src.metadata.file_tags import extract_file_metadata
from src.metadata.lastfm import fetch_artist_info, fetch_similar_tracks, fetch_track_info
from src.metadata.musicbrainz import fetch_musicbrainz_data
from src.metadata.spotify import fetch_spotify_info, get_token

logger = logging.getLogger(__name__)


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

    acoustid_recording_id, aid_title, aid_artist = get_acoustid_metadata(audio_path, acoustid_api_key)

    if not aid_title and not aid_artist:
        logger.warning("[Metadata] No AcoustID match for %s — skipping", audio_path.name)
        return {}

    # Split "David Guetta feat. Kid Cudi" → artist + featured artists
    raw_aid_artist = aid_artist or ""
    artist, aid_feat = split_artist_featuring(raw_aid_artist)
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
        track_info = fetch_track_info(title, artist, lastfm_api_key)
        if track_info:
            artist_name = str(track_info.get("artist") or artist)
            artist_info = fetch_artist_info(artist_name, lastfm_api_key) or {}
            similar = fetch_similar_tracks(title, artist_name, lastfm_api_key)

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
        token = get_token(spotify_client_id, spotify_client_secret)
        if token:
            spotify_info = fetch_spotify_info(mb_title, mb_artist, token)
            if not spotify_info and raw_aid_artist and raw_aid_artist != mb_artist:
                # Try with full credit string (e.g. "David Guetta feat. Kid Cudi") in case Spotify needs it
                spotify_info = fetch_spotify_info(mb_title, raw_aid_artist, token)

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
    mb_data = fetch_musicbrainz_data(
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
    all_featured = dedup_featured_artists(all_featured)
    if all_featured:
        result["featured_artists"] = all_featured
        logger.info("[Metadata] Featured artists: %s", all_featured)

    # Use the best release date across Spotify and MusicBrainz (more precise and/or earlier wins)
    mb_release_date: str | None = mb_data.get("release_date")  # type: ignore[assignment]
    if mb_release_date:
        current_date = str(result.get("release_date") or "")
        best_date = better_date(current_date, mb_release_date)
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
