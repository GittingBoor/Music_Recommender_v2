import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from src.api.heartbeat import run_with_heartbeat
from src.api.routes.admin import process_audio_file
from src.core.config import SUPPORTED_AUDIO_EXTENSIONS, settings
from src.ingest.failures import record_failure
from src.ingest.tracker import Stage, tracker

logger = logging.getLogger(__name__)
router = APIRouter()

_UPLOADS_DIR = settings.datasets_dir / "uploads"

# Characters that are unsafe in filenames on any platform.
_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_name(name: str) -> str:
    """Sanitise an upload filename to avoid path traversal or OS issues."""
    name = Path(name).name  # strip any path components
    name = _UNSAFE_RE.sub("_", name)
    return name or "upload"


def _unique_path(dest_dir: Path, filename: str) -> Path:
    """Return a path that doesn't conflict with existing files.

    If 'song.mp3' already exists, tries 'song_1.mp3', 'song_2.mp3', …
    """
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = dest_dir / filename
    counter = 1
    while candidate.exists():
        candidate = dest_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def _analyse_upload(dest: Path, original_name: str, job_id: int) -> Iterator[str]:
    """Analyse ``dest`` off the event loop and stream the result as JSON.

    While the analysis runs, single spaces keep the connection alive
    (leading whitespace is valid JSON, so ``res.json()`` still works).
    """
    result: dict = {}
    try:
        for outcome in run_with_heartbeat(lambda: process_audio_file(dest, job_id)):
            if outcome is None:
                yield " "
            else:
                result = outcome
    finally:
        tracker.remove(job_id)
    result["filename"] = original_name
    record_failure("upload", original_name, result)

    # Clean up if not saved — only successfully processed files stay in datasets/.
    if result["status"] != "saved":
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass

    yield json.dumps(result)


@router.post("/upload", response_model=None)
async def upload_song(file: UploadFile = File(...)) -> dict | StreamingResponse:
    """Upload a single audio file, run it through the analysis pipeline,
    and save it to ``datasets/uploads/`` if successful.

    Returns:
        status  : "saved" | "skipped" | "error"
        reason  : str | None
        title   : str | None
        artist  : str | None
        song_id : str | None
        filename: str  (original client filename)
    """
    original_name = file.filename or "upload"
    suffix = Path(original_name).suffix.lower()

    if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
        record_failure("upload", original_name, {"status": "skipped", "reason": "unsupported_format"})
        return {
            "status": "skipped",
            "reason": "unsupported_format",
            "title": None,
            "artist": None,
            "song_id": None,
            "filename": original_name,
        }

    # Write the uploaded bytes to a unique path under uploads/.
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(original_name)
    dest = _unique_path(_UPLOADS_DIR, safe)

    try:
        content = await file.read()
        dest.write_bytes(content)
    except Exception as exc:
        logger.error("[Upload] Failed to write %s: %s", original_name, exc)
        record_failure("upload", original_name, {"status": "error", "reason": f"write_error: {exc}"})
        return {
            "status": "error",
            "reason": f"write_error: {exc}",
            "title": None,
            "artist": None,
            "song_id": None,
            "filename": original_name,
        }

    job_id = tracker.add("upload", original_name, Stage.WAITING)
    return StreamingResponse(
        _analyse_upload(dest, original_name, job_id),
        media_type="application/json",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
