import logging
import re
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from src.api.routes.admin import process_audio_file
from src.core.config import SUPPORTED_AUDIO_EXTENSIONS, settings

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


@router.post("/upload")
async def upload_song(file: UploadFile = File(...)) -> dict:
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
        return {
            "status": "error",
            "reason": f"write_error: {exc}",
            "title": None,
            "artist": None,
            "song_id": None,
            "filename": original_name,
        }

    result = process_audio_file(dest)
    result["filename"] = original_name

    # Clean up if not saved — only successfully processed files stay in datasets/.
    if result["status"] != "saved":
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass

    return result
