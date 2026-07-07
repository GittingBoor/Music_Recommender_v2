"""AcoustID fingerprinting client.

Named ``acoustid_client`` to avoid confusion with the ``acoustid`` pip
package (pyacoustid) that it wraps.
"""
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

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


def _probe_key(api_key: str) -> None:
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


def get_acoustid_metadata(
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
        _probe_key(api_key)
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


def get_recording_id(audio_path: Path, api_key: str) -> str | None:
    recording_id, _, _ = get_acoustid_metadata(audio_path, api_key)
    return recording_id
