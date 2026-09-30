import logging
import threading
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session, selectinload

from src.api.deps import get_db
from src.core.config import SUPPORTED_AUDIO_EXTENSIONS, settings
from src.db.models import Song, TrackMetadata
from src.db.session import get_session
from src.ingest.failures import record_failure
from src.ingest.tracker import Stage, tracker
from src.metadata.identity import IdentityHint, MetadataSource, SongOrigin
from src.metadata.musicbrainz import fetch_recording_identity

logger = logging.getLogger(__name__)
router = APIRouter()


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

# The cached Essentia model instances are shared and not thread-safe, and two
# analyses at once saturate the mini-PC. Parallel requests queue up here.
_ANALYSIS_LOCK = threading.Lock()


def process_audio_file(
    audio_file: Path,
    job_id: int | None = None,
    hint: IdentityHint | None = None,
    origin: SongOrigin | None = None,
) -> dict:
    """Run the full ingest pipeline on a single audio file.

    The duration gate and the metadata lookup (AcoustID, MusicBrainz, Last.fm,
    Spotify, duplicate check) mostly wait on the network, so they run before
    the analysis lock: the next song gets identified while the current one is
    analysed. Only DSP/ML analysis, DB save and the UMAP update hold the lock.

    Returns a dict with keys:
        status  : "saved" | "skipped" | "error"
        reason  : str | None  (None when saved successfully)
        title   : str | None
        artist  : str | None
        song_id : str | None

    ``job_id`` is the song's entry in the pipeline tracker, if any; it shows
    as waiting until the analysis lock is free, then as analysing.
    ``hint`` names the song when AcoustID does not know it (video title,
    user input). ``origin`` is the upload filename or YouTube video the audio
    came from; it is stored with the song.
    """
    if job_id is not None:
        tracker.update(job_id, stage=Stage.WAITING)
    try:
        identified = _identify(audio_file, hint)
        if "status" in identified:
            return identified
        with _ANALYSIS_LOCK:
            if job_id is not None:
                tracker.update(job_id, stage=Stage.ANALYZING)
            return _analyse(audio_file, identified["metadata"], identified["song_id"], origin)
    except Exception as exc:
        logger.error("[Ingest] Failed %s: %s", audio_file.name, exc)
        return {"status": "error", "reason": str(exc),
                "title": None, "artist": None, "song_id": None}


def _identify(audio_file: Path, hint: IdentityHint | None) -> dict:
    """Duration gate and metadata lookup, no analysis lock needed.

    Returns a finished skip result (has ``status``), or ``{"metadata", "song_id"}``
    for a song to analyse.
    """
    from src.analysis.pipeline import precheck_skip

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
    skip_reason, metadata, song_id = precheck_skip(audio_file, hint)
    if skip_reason:
        logger.info("[Ingest] Skipping %s — %s", audio_file.name, skip_reason)
        return _skipped(skip_reason, metadata, song_id)
    return {"metadata": metadata, "song_id": song_id}


def _analyse(audio_file: Path, metadata: dict, song_id: str | None, origin: SongOrigin | None) -> dict:
    """DSP/ML analysis and save; call with the analysis lock held."""
    from src.analysis.pipeline import _save_to_database
    from src.analysis.worker import get_analysis_worker

    # Another download of the same song may have been saved while this one was identified.
    if _already_saved(song_id, metadata.get("acoustid_id")):
        logger.info("[Ingest] Skipping %s — duplicate (saved meanwhile)", audio_file.name)
        return _skipped("duplicate", metadata, song_id)

    logger.info("[Ingest] Processing %s", audio_file.name)
    result = get_analysis_worker().analyse(audio_file, metadata)
    _save_to_database(result, audio_file, origin)

    title  = str((result.get("metadata") or {}).get("title")  or "") or None
    artist = str((result.get("metadata") or {}).get("artist") or "") or None

    if title and song_id:
        _update_umap_for_song(song_id)

    return {"status": "saved", "reason": None,
            "title": title, "artist": artist, "song_id": song_id}


def _skipped(reason: str, metadata: dict | None, song_id: str | None) -> dict:
    title = str((metadata or {}).get("title") or "") or None
    artist = str((metadata or {}).get("artist") or "") or None
    return {"status": "skipped", "reason": reason, "title": title, "artist": artist, "song_id": song_id}


def _already_saved(song_id: str | None, acoustid_id: object) -> bool:
    """True when a song with this id or AcoustID recording is already in the library."""
    session = get_session()
    try:
        if song_id and session.get(Song, song_id):
            return True
        return bool(acoustid_id) and session.query(Song.id).filter(Song.acoustid_id == acoustid_id).first() is not None
    finally:
        session.close()


def _run_ingest() -> None:
    audio_files = sorted(
        f for f in settings.datasets_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    )
    logger.info("[Admin] Ingesting %d files from %s", len(audio_files), settings.datasets_dir)

    for audio_file in audio_files:
        result = process_audio_file(audio_file)
        record_failure("folder", audio_file.name, result)

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


# ── songs without an AcoustID recording (admin-only, nginx keeps /admin/ internal) ──

class UnverifiedSongOut(BaseModel):
    id: str
    title: str | None
    artist: str | None
    metadata_source: str
    metadata_reviewed: bool


class AcoustidUpdate(BaseModel):
    acoustid_id: str = Field(min_length=36, max_length=36, description="MusicBrainz recording UUID")


@router.get("/admin/songs/missing-acoustid", response_model=list[UnverifiedSongOut])
def songs_missing_acoustid(db: Session = Depends(get_db)) -> list[UnverifiedSongOut]:
    """Songs without an AcoustID recording that no admin has checked yet."""
    rows = (
        db.query(Song)
        .filter(Song.acoustid_id.is_(None), Song.metadata_reviewed.is_(False))
        .order_by(Song.artist, Song.title)
        .all()
    )
    return [_unverified_out(s) for s in rows]


@router.put("/admin/songs/{song_id}/acoustid", response_model=UnverifiedSongOut)
def set_song_acoustid(song_id: str, body: AcoustidUpdate, db: Session = Depends(get_db)) -> UnverifiedSongOut:
    """Attach the recording id an admin looked up; title and artists are then taken from that recording.

    The song keeps its id, so its features and links stay intact.
    """
    song = _get_song_or_404(db, song_id)
    owner = db.query(Song.id).filter(Song.acoustid_id == body.acoustid_id, Song.id != song_id).first()
    if owner:
        raise HTTPException(
            status_code=409,
            detail=f"Recording {body.acoustid_id} already belongs to song {owner.id}",
        )
    identity = fetch_recording_identity(body.acoustid_id)
    if identity is None:
        raise HTTPException(
            status_code=502,
            detail=f"MusicBrainz returned no title/artist for recording {body.acoustid_id}; "
                   "check the id and try again",
        )
    song.acoustid_id = body.acoustid_id
    song.title = identity.title
    song.artist = identity.artist
    song.metadata_source = MetadataSource.ACOUSTID.value
    song.metadata_reviewed = True
    track = db.get(TrackMetadata, song_id)
    if track is not None:
        track.featured_artists = identity.featured_artists
    db.commit()
    logger.info("[Admin] %s renamed from recording %s: %s — %s",
                song_id, body.acoustid_id, identity.artist, identity.title)
    return _unverified_out(song)


@router.put("/admin/songs/{song_id}/reviewed", response_model=UnverifiedSongOut)
def mark_song_reviewed(song_id: str, db: Session = Depends(get_db)) -> UnverifiedSongOut:
    """Confirm that a song without AcoustID recording is named correctly."""
    song = _get_song_or_404(db, song_id)
    song.metadata_reviewed = True
    db.commit()
    return _unverified_out(song)


def _get_song_or_404(db: Session, song_id: str) -> Song:
    song = db.get(Song, song_id)
    if song is None:
        raise HTTPException(status_code=404, detail=f"No song with id {song_id!r}")
    return song


def _unverified_out(song: Song) -> UnverifiedSongOut:
    return UnverifiedSongOut(
        id=song.id, title=song.title, artist=song.artist,
        metadata_source=song.metadata_source, metadata_reviewed=song.metadata_reviewed,
    )
