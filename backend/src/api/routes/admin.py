import logging
import subprocess
from pathlib import Path

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session, selectinload

from src.api.deps import get_db
from src.core.config import SUPPORTED_AUDIO_EXTENSIONS, settings
from src.db.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter()

_PREVIEW_SECONDS = 15


@router.delete("/admin/clear")
def clear_database(db: Session = Depends(get_db)):
    """Truncate all song-related tables and reset UMAP state."""
    from src.analysis.umap_generator import get_umap_state
    get_umap_state().reset()

    db.execute(text("""
        TRUNCATE TABLE
            artists,
            instruments,
            detailed_genres,
            parent_genres,
            ml_mood_features,
            ml_profile_features,
            dsp_features,
            track_metadata,
            file_metadata,
            songs
        RESTART IDENTITY CASCADE
    """))
    db.commit()
    logger.info("[Admin] Database cleared")
    return {"status": "cleared"}


def _find_exciting_start(dsp: dict, total_seconds: float) -> int:
    """Find the start second of the most energetic 15-second window."""
    loudness = dsp.get("loudness_short_term_timeseries") or []
    flux = dsp.get("spectral_flux_timeseries") or []

    n = int(min(total_seconds, len(loudness))) if loudness else int(total_seconds)
    if n < _PREVIEW_SECONDS + 10:
        return max(0, (n - _PREVIEW_SECONDS) // 2)

    def _norm(ts: list) -> np.ndarray:
        arr = np.array(ts[:n], dtype=float)
        lo, hi = arr.min(), arr.max()
        return (arr - lo) / (hi - lo + 1e-8)

    score = _norm(loudness[:n]) if loudness else np.zeros(n)
    if flux and len(flux) >= n:
        score = score * 0.6 + _norm(flux[:n]) * 0.4

    skip_start = max(10, int(n * 0.15))
    skip_end = max(10, int(n * 0.10))
    window = _PREVIEW_SECONDS

    best_start = skip_start
    best_val = -1.0
    for i in range(skip_start, n - skip_end - window):
        avg = float(score[i: i + window].mean())
        if avg > best_val:
            best_val = avg
            best_start = i

    return best_start


def _extract_preview(audio_path: Path, dsp: dict, song_id: str) -> None:
    """Extract a 15-second highlight clip and save to short_audio/."""
    output_path = settings.short_audio_dir / f"{song_id}.mp3"
    if output_path.exists():
        return

    duration = dsp.get("duration_seconds") or 0.0
    if duration < 5:
        return

    start = _find_exciting_start(dsp, duration)
    settings.short_audio_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(audio_path),
            "-ss", str(start),
            "-t", str(_PREVIEW_SECONDS),
            "-b:a", "128k",
            str(output_path),
        ],
        capture_output=True,
    )
    if proc.returncode == 0:
        logger.info("[Preview] Saved %s (start=%ds)", song_id, start)
    else:
        logger.error("[Preview] ffmpeg failed for %s: %s", song_id, proc.stderr.decode())


def _update_umap_for_song(song_id: str) -> None:
    from src.analysis.umap_generator import get_umap_state, ALL_FEATURES, MIN_FIT_SONGS
    from src.db.models import Song

    state = get_umap_state()
    session = get_session()
    try:
        total = session.query(Song).count()

        if not state.is_fitted:
            if total < MIN_FIT_SONGS:
                return
            songs = (
                session.query(Song)
                .options(
                    selectinload(Song.dsp_features),
                    selectinload(Song.ml_moods),
                    selectinload(Song.ml_profile),
                )
                .all()
            )
            state.fit(songs, ALL_FEATURES)
        else:
            song = (
                session.query(Song)
                .options(
                    selectinload(Song.dsp_features),
                    selectinload(Song.ml_moods),
                    selectinload(Song.ml_profile),
                )
                .filter(Song.id == song_id)
                .first()
            )
            if song:
                state.add_songs([song])
    finally:
        session.close()


def _final_umap_refit() -> None:
    from src.analysis.umap_generator import get_umap_state, ALL_FEATURES
    from src.db.models import Song

    state = get_umap_state()
    session = get_session()
    try:
        songs = (
            session.query(Song)
            .options(
                selectinload(Song.dsp_features),
                selectinload(Song.ml_moods),
                selectinload(Song.ml_profile),
            )
            .all()
        )
        if songs:
            feature_keys = state.feature_keys or ALL_FEATURES
            logger.info("[Admin] Final UMAP refit on %d songs", len(songs))
            state.fit(songs, feature_keys)
    finally:
        session.close()


def _get_duration_seconds(audio_path: Path) -> float | None:
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(audio_path)
        if audio and hasattr(audio, "info"):
            return float(audio.info.length)
    except Exception:
        pass
    return None


def _is_recognized_by_acoustid(audio_path: Path, api_key: str) -> bool:
    """Quick AcoustID fingerprint check — returns True if match score >= 0.5."""
    try:
        import acoustid
        duration, fingerprint = acoustid.fingerprint_file(str(audio_path))
        if not fingerprint or duration <= 0:
            return False
        response = acoustid.lookup(api_key, fingerprint, duration)
        matches = list(acoustid.parse_lookup_result(response))
        return bool(matches) and max(m[0] for m in matches) >= 0.5
    except Exception as exc:
        logger.warning("[AcoustID] Quick check failed for %s: %s", audio_path.name, exc)
        return False


_MAX_DURATION_WITHOUT_RECOGNITION = 600.0  # 10 minutes


def process_audio_file(audio_file: Path) -> dict:
    """Run the full ingest pipeline on a single audio file.

    Performs the duration gate, precheck_skip, DSP/ML analysis, DB save,
    preview extraction, and incremental UMAP update.

    Returns a dict with keys:
        status  : "saved" | "skipped" | "error"
        reason  : str | None  (None when saved successfully)
        title   : str | None
        artist  : str | None
        song_id : str | None
    """
    from src.analysis.pipeline import run_full_pipeline, _save_to_database, precheck_skip

    try:
        # Duration gate: skip files >10 min that aren't recognised by AcoustID.
        duration = _get_duration_seconds(audio_file)
        if duration is not None and duration > _MAX_DURATION_WITHOUT_RECOGNITION:
            api_key = settings.acoustid_api_key or ""
            recognized = _is_recognized_by_acoustid(audio_file, api_key) if api_key else False
            if not recognized:
                logger.info(
                    "[Ingest] Skipping %s — duration=%.0fs (>10min) and not recognized by AcoustID",
                    audio_file.name, duration,
                )
                return {"status": "skipped", "reason": "too_long_unrecognized",
                        "title": None, "artist": None, "song_id": None}

        # Early-skip: metadata + AcoustID + duplicate check BEFORE heavy analysis.
        skip_reason, metadata, song_id = precheck_skip(audio_file)
        if skip_reason:
            logger.info("[Ingest] Skipping %s — %s", audio_file.name, skip_reason)
            title  = str((metadata or {}).get("title")  or "") or None
            artist = str((metadata or {}).get("artist") or "") or None
            return {"status": "skipped", "reason": skip_reason,
                    "title": title, "artist": artist, "song_id": song_id}

        logger.info("[Ingest] Processing %s", audio_file.name)
        result = run_full_pipeline(audio_file, metadata=metadata)
        _save_to_database(result, audio_file)

        title  = str((result.get("metadata") or {}).get("title")  or "") or None
        artist = str((result.get("metadata") or {}).get("artist") or "") or None

        if title and song_id:
            _extract_preview(audio_file, result.get("dsp") or {}, song_id)
            _update_umap_for_song(song_id)

        return {"status": "saved", "reason": None,
                "title": title, "artist": artist, "song_id": song_id}

    except Exception as exc:
        logger.error("[Ingest] Failed %s: %s", audio_file.name, exc)
        return {"status": "error", "reason": str(exc),
                "title": None, "artist": None, "song_id": None}


def _run_ingest() -> None:
    audio_files = sorted(
        f for f in settings.datasets_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    )
    logger.info("[Admin] Ingesting %d files from %s", len(audio_files), settings.datasets_dir)

    for audio_file in audio_files:
        process_audio_file(audio_file)

    _final_umap_refit()
    logger.info("[Admin] Ingestion complete")


@router.post("/admin/ingest")
def ingest_dataset(background_tasks: BackgroundTasks):
    if not settings.datasets_dir.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Datasets directory not found: {settings.datasets_dir}",
        )

    file_count = sum(
        1 for f in settings.datasets_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    )
    background_tasks.add_task(_run_ingest)
    return {"status": "started", "file_count": file_count}
