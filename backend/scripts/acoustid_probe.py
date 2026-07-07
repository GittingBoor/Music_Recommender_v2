"""
Test script for inspecting the raw AcoustID + MusicBrainz response for a given audio file.

Flow:
  1. Fingerprint the file via fpcalc (AcoustID)
  2. Look up the fingerprint at api.acoustid.org → get AcoustID track IDs + MusicBrainz recording IDs
  3. For each recording ID, query MusicBrainz directly → get full title/artist/release data

Usage:
    python tests/test_acoustid.py <audio_file> [--key YOUR_API_KEY]

If --key is omitted, the key is read from backend/.env (ACOUSTID_API_KEY).
"""

import argparse
import json
import logging
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)-8s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("acoustid_test")

_ACOUSTID_URL = "https://api.acoustid.org/v2/lookup"
_MB_URL = "https://musicbrainz.org/ws/2/recording"
# recordings: MB recording IDs linked to the fingerprint
# releases/tracks: release + track-level titles (where "(Edit)" variants appear)
# sources: how many users submitted this fingerprint
_META_FIELDS = "recordings releases tracks releasegroups sources usermeta"


def _load_key_from_env(env_path: Path) -> str:
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("ACOUSTID_API_KEY"):
            _, _, value = line.partition("=")
            return value.strip().strip('"').strip("'")
    return ""


def _file_info(path: Path) -> None:
    import os
    stat = os.stat(path)
    size_mb = stat.st_size / (1024 * 1024)
    logger.info("File path  : %s", path.resolve())
    logger.info("File size  : %.2f MB (%d bytes)", size_mb, stat.st_size)
    logger.info("Extension  : %s", path.suffix.lower())

    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(path)
        if audio and hasattr(audio, "info"):
            logger.info("Duration   : %.2f seconds", audio.info.length)
            logger.info("Bitrate    : %s bps", getattr(audio.info, "bitrate", "n/a"))
            logger.info("Sample rate: %s Hz", getattr(audio.info, "sample_rate", "n/a"))
        tags = audio.tags if audio and audio.tags else {}
        if tags:
            logger.info("Embedded tags:")
            for k, v in sorted(tags.items()):
                logger.info("  %-20s = %r", k, v)
        else:
            logger.info("Embedded tags: none")
    except Exception as exc:
        logger.warning("mutagen read failed: %s", exc)


def _fingerprint(path: Path) -> tuple[float, str] | None:
    try:
        import acoustid
    except ImportError:
        logger.error("pyacoustid not installed — run: pip install pyacoustid")
        return None

    logger.info("Generating fingerprint via fpcalc …")
    try:
        duration, fingerprint = acoustid.fingerprint_file(str(path))
        logger.info("Duration (fpcalc) : %.2f seconds", duration)
        logger.info("Fingerprint length: %d chars", len(fingerprint) if fingerprint else 0)
        logger.debug("Fingerprint (first 120 chars): %s…", (fingerprint or b"")[:120])
        return float(duration), fingerprint
    except acoustid.FingerprintGenerationError as exc:
        logger.error("Fingerprint generation failed: %s", exc)
        return None
    except Exception as exc:
        logger.error("Unexpected error during fingerprinting (%s): %s", type(exc).__name__, exc)
        return None


def _acoustid_lookup(api_key: str, fingerprint: str, duration: float) -> dict | None:
    params = urllib.parse.urlencode({
        "client": api_key,
        "meta": _META_FIELDS,
        "duration": str(int(duration)),
        "fingerprint": fingerprint,
    }).encode()

    req = urllib.request.Request(
        _ACOUSTID_URL,
        data=params,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    logger.info("Querying AcoustID (meta=%r) …", _META_FIELDS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode())
            logger.error("AcoustID HTTP %s: %s", exc.code, json.dumps(data, indent=2))
        except Exception:
            logger.error("AcoustID HTTP %s — unreadable body", exc.code)
        return None
    except Exception as exc:
        logger.error("AcoustID request failed (%s): %s", type(exc).__name__, exc)
        return None


def _mb_lookup(recording_id: str) -> dict | None:
    """Query MusicBrainz for full recording metadata including all releases."""
    url = (
        f"{_MB_URL}/{recording_id}"
        f"?inc=artists+releases+release-groups+media"
        f"&fmt=json"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MusicRecommender/1.0 (debug-test)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode())
            logger.error("MusicBrainz HTTP %s for %s: %s", exc.code, recording_id, data)
        except Exception:
            logger.error("MusicBrainz HTTP %s for %s — unreadable body", exc.code, recording_id)
        return None
    except Exception as exc:
        logger.error("MusicBrainz request failed (%s): %s", type(exc).__name__, exc)
        return None


def _log_mb_recording(recording_id: str, idx: int) -> None:
    logger.info("  ┌─ MusicBrainz lookup for recording %s", recording_id)
    data = _mb_lookup(recording_id)
    if data is None:
        logger.warning("  └─ No data returned from MusicBrainz")
        return

    mb_title = data.get("title") or "—"
    mb_length = data.get("length")
    mb_artists = data.get("artist-credit") or []
    mb_artist_str = "".join(
        (a.get("name") or a.get("artist", {}).get("name") or "") + a.get("joinphrase", "")
        for a in mb_artists
    ).strip() or "—"

    logger.info("  │  Title       : %r", mb_title)
    logger.info("  │  Artist      : %r", mb_artist_str)
    logger.info("  │  Length      : %s ms", mb_length or "—")

    releases: list[dict] = data.get("releases") or []
    logger.info("  │  Releases (%d) — these are all title variants:", len(releases))
    for rel in releases:
        rel_id    = rel.get("id", "—")[:8]
        rel_title = rel.get("title") or "—"
        rel_date  = rel.get("date") or "?"
        rel_type  = rel.get("release-group", {}).get("primary-type") or "?"
        # Track title may differ from recording title (e.g. "Whatever (Edit)")
        media: list[dict] = rel.get("media") or []
        track_title: str | None = None
        for medium in media:
            for track in medium.get("tracks") or []:
                if track.get("recording", {}).get("id") == recording_id:
                    track_title = track.get("title")
                    break
        differs = " ◄ DIFFERS FROM RECORDING TITLE" if track_title and track_title != mb_title else ""
        logger.info(
            "  │    [%s] %r  track=%r  date=%s  type=%s%s",
            rel_id, rel_title, track_title, rel_date, rel_type, differs,
        )

    logger.info("  └─ end recording %s", recording_id)


def _log_acoustid_results(data: dict) -> list[str]:
    """Log AcoustID results and return all found recording IDs."""
    status = data.get("status")
    logger.info("=" * 60)
    logger.info("STEP 2 — AcoustID Results")
    logger.info("=" * 60)
    logger.info("Status: %s", status)

    if status != "ok":
        error = data.get("error") or {}
        logger.error("Error code   : %s", error.get("code"))
        logger.error("Error message: %s", error.get("message"))
        return []

    results: list[dict] = data.get("results") or []
    logger.info("Matches returned: %d", len(results))

    if not results:
        logger.warning("No matches — fingerprint not recognised by AcoustID.")
        logger.warning("This song may not be in the AcoustID database yet.")
        return []

    recording_ids: list[str] = []

    for r_idx, result in enumerate(results):
        score: float = result.get("score", 0.0)
        acoustid_id: str = result.get("id", "—")
        recordings: list[dict] = result.get("recordings") or []

        logger.info("─" * 60)
        logger.info("Match #%d", r_idx + 1)
        logger.info("  AcoustID track ID : %s", acoustid_id)
        logger.info("  Score             : %.4f  %s", score, "(✓ above 0.5 threshold)" if score >= 0.5 else "(✗ below threshold — would be discarded)")
        logger.info("  Linked recordings : %d", len(recordings))

        if not recordings:
            logger.warning("  → No MusicBrainz recordings linked to this AcoustID track.")
            logger.warning("    This means the fingerprint is known but has no MB metadata attached.")
        else:
            for rec in recordings:
                rec_id = rec.get("id")
                rec_title = rec.get("title") or "—"
                rec_artists = rec.get("artists") or []
                rec_artist_str = ", ".join(
                    a if isinstance(a, str) else a.get("name", "?") for a in rec_artists
                ) or "—"
                sources = rec.get("sources") or "—"
                logger.info(
                    "  · MB recording: %s  title=%r  artist=%r  sources=%s",
                    rec_id, rec_title, rec_artist_str, sources,
                )
                if rec_id and rec_id not in recording_ids:
                    recording_ids.append(rec_id)

    return recording_ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect raw AcoustID + MusicBrainz response for an audio file"
    )
    parser.add_argument("file", type=Path, help="Path to the audio file")
    parser.add_argument("--key", default="", help="AcoustID API key (overrides .env)")
    parser.add_argument(
        "--no-mb", action="store_true",
        help="Skip MusicBrainz lookup (only show AcoustID results)",
    )
    args = parser.parse_args()

    audio_path: Path = args.file
    if not audio_path.exists():
        logger.error("File not found: %s", audio_path)
        sys.exit(1)

    api_key: str = args.key
    if not api_key:
        env_path = Path(__file__).parent.parent / ".env"
        api_key = _load_key_from_env(env_path)
    if not api_key:
        logger.error("No AcoustID API key found. Use --key or set ACOUSTID_API_KEY in backend/.env")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("STEP 1 — File Info & Fingerprint")
    logger.info("=" * 60)
    _file_info(audio_path)

    result = _fingerprint(audio_path)
    if result is None:
        sys.exit(1)
    duration, fingerprint = result

    acoustid_data = _acoustid_lookup(api_key, fingerprint, duration)
    if acoustid_data is None:
        sys.exit(1)

    recording_ids = _log_acoustid_results(acoustid_data)

    if not recording_ids:
        logger.warning("No MusicBrainz recording IDs found — cannot do MB lookup.")
        logger.warning("The title '(Edit)' problem cannot occur here since there's no MB data.")
        sys.exit(0)

    if args.no_mb:
        logger.info("Skipping MusicBrainz lookup (--no-mb flag set).")
        sys.exit(0)

    logger.info("=" * 60)
    logger.info("STEP 3 — MusicBrainz Lookup (%d recording(s))", len(recording_ids))
    logger.info("=" * 60)
    logger.info("This is where title variants like '(Edit)', '(Radio Edit)' come from.")

    for idx, rec_id in enumerate(recording_ids):
        _log_mb_recording(rec_id, idx)
        if idx < len(recording_ids) - 1:
            time.sleep(1.1)  # MusicBrainz rate limit: max 1 req/s


if __name__ == "__main__":
    main()
