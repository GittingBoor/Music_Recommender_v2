"""Persist songs that did not make it into the library (table ingest_failures)."""
import logging

from src.db.models import IngestFailure
from src.db.session import get_session

logger = logging.getLogger(__name__)

# Reasons that are a verdict on the song, not a crash; everything else from
# process_audio_file with status "error" is an exception message.
_KNOWN_REASONS = {
    "no_acoustid_match",
    "duplicate",
    "too_long_unrecognized",
    "unsupported_format",
    "no_search_hit",
    "all_hits_in_library",
}


def _split_reason(result: dict) -> tuple[str, str | None]:
    """Turn a pipeline result into (reason category, human-readable detail)."""
    raw = str(result.get("reason") or "unknown")
    error = result.get("error") or None

    if raw in _KNOWN_REASONS:
        reason, detail = raw, None
    elif raw.startswith(("download_error", "write_error")):
        reason, _, detail = raw.partition(":")
        detail = detail.strip() or None
    else:
        reason, detail = "error", raw

    if isinstance(error, dict):
        extra = error.get("raw_message") or error.get("explanation")
        if extra:
            detail = f"{detail} — {extra}" if detail else str(extra)
    return reason, detail


def record_failure(source: str, label: str, result: dict, video_id: str | None = None,
                   note: str | None = None) -> None:
    """Store a failed or skipped ingest. Never raises: logging must not break ingest."""
    if result.get("status") == "saved":
        return
    reason, detail = _split_reason(result)
    if note:
        detail = f"{detail} ({note})" if detail else note
    session = get_session()
    try:
        session.add(IngestFailure(
            source=source,
            label=label[:512],
            video_id=video_id,
            status=str(result.get("status") or "error")[:16],
            reason=reason[:64],
            detail=detail,
            title=(result.get("title") or None),
            artist=(result.get("artist") or None),
            song_id=result.get("song_id"),
        ))
        session.commit()
        logger.info("[Ingest] Not added: %s — %s", label, reason)
    except Exception as exc:
        session.rollback()
        logger.error("[Ingest] Could not record failure for %s: %s", label, exc)
    finally:
        session.close()
