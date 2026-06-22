import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from src.analysis.embeddings import extract_effnet_embedding, extract_musicnn_embedding
from src.analysis.classifiers import (
    predict_mood_happy,
    predict_mood_sad,
    predict_mood_aggressive,
    predict_mood_party,
    predict_mood_relaxed,
    predict_mood_acoustic,
    predict_mood_electronic,
    predict_arousal_valence,
    predict_genre_discogs400,
    predict_approachability,
    predict_engagement,
    predict_instrument,
    predict_voice_instrumental,
    predict_gender,
)
from src.analysis.dsp import extract_all_dsp_features
from src.analysis.metadata import extract_all_metadata
from src.analysis.model_manager import get_manager
from src.analysis.other_features import extract_other_features
from src.core.config import settings

logger = logging.getLogger(__name__)

_TEST_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "test_output"

_SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".m4a"}

_EFFNET_CLASSIFIERS: dict[str, Callable[[np.ndarray], object]] = {
    "mood_happy": predict_mood_happy,
    "mood_sad": predict_mood_sad,
    "mood_aggressive": predict_mood_aggressive,
    "mood_party": predict_mood_party,
    "mood_relaxed": predict_mood_relaxed,
    "mood_acoustic": predict_mood_acoustic,
    "mood_electronic": predict_mood_electronic,
    "genre_discogs400": predict_genre_discogs400,
    "approachability": predict_approachability,
    "engagement": predict_engagement,
    "voice_instrumental": predict_voice_instrumental,
    "gender": predict_gender,
    "instrument": predict_instrument,
}

_MUSICNN_CLASSIFIERS: dict[str, Callable[[np.ndarray], object]] = {
    "arousal_valence": predict_arousal_valence,
}

ALL_MODEL_KEYS: list[str] = list(_EFFNET_CLASSIFIERS) + list(_MUSICNN_CLASSIFIERS)


def ensure_models(keys: list[str] | None = None) -> None:
    """Download any missing models before running the pipeline."""
    manager = get_manager()
    target_keys = keys or ALL_MODEL_KEYS

    embedding_keys: set[str] = set()
    for key in target_keys:
        embedding_keys.add("musicnn_embedding" if key in _MUSICNN_CLASSIFIERS else "effnet_embedding")

    all_required = list(embedding_keys) + target_keys
    missing = [k for k in all_required if not manager.is_cached(k)]

    if not missing:
        logger.info("[Pipeline] All required models cached")
        return

    logger.info("[Pipeline] Downloading %d missing model(s): %s", len(missing), missing)
    for key in missing:
        manager.ensure_key(key)
    logger.info("[Pipeline] All models ready")


def _run_effnet_classifiers(audio_path: Path, keys: list[str]) -> dict[str, object]:
    """Compute EffNet embedding once, then run all specified EffNet classifiers."""
    embedding = extract_effnet_embedding(audio_path)
    results: dict[str, object] = {}
    for key in keys:
        logger.info("[ML] Running %s", key)
        results[key] = _EFFNET_CLASSIFIERS[key](embedding)
        logger.info("[ML] %s complete", key)
    return results


def _run_musicnn_classifiers(audio_path: Path, keys: list[str]) -> dict[str, object]:
    """Compute MusiCNN embedding once, then run all specified MusiCNN classifiers."""
    embedding = extract_musicnn_embedding(audio_path)
    results: dict[str, object] = {}
    for key in keys:
        logger.info("[ML] Running %s", key)
        results[key] = _MUSICNN_CLASSIFIERS[key](embedding)
        logger.info("[ML] %s complete", key)
    return results


_MOOD_KEYS = {"mood_happy", "mood_sad", "mood_aggressive", "mood_party", "mood_relaxed", "mood_acoustic", "mood_electronic"}


def _structure_ml_results(flat: dict[str, object]) -> dict[str, object]:
    """Reorganise flat ML results into grouped sub-dicts."""
    moods = {key.replace("mood_", ""): flat[key] for key in _MOOD_KEYS if key in flat}
    profile = {
        "approachability": flat.get("approachability"),
        "engagement": flat.get("engagement"),
        "voice_instrumental": flat.get("voice_instrumental"),
        "gender": flat.get("gender"),
        "arousal_valence": flat.get("arousal_valence"),
    }
    return {
        "moods": moods,
        "genre_discogs400": flat.get("genre_discogs400"),
        "profile": profile,
        "instrument": flat.get("instrument"),
    }


def run_full_pipeline(audio_path: Path) -> dict[str, object]:
    """Run metadata extraction, DSP, and all ML models on an audio file."""
    logger.info("[Pipeline] Starting full pipeline — %s", audio_path.name)
    ensure_models()

    metadata = extract_all_metadata(
        audio_path,
        lastfm_api_key=settings.lastfm_api_key,
        acoustid_api_key=settings.acoustid_api_key,
        spotify_client_id=settings.spotify_client_id,
        spotify_client_secret=settings.spotify_client_secret,
    )
    logger.info("[Pipeline] Metadata complete")

    dsp = extract_all_dsp_features(audio_path)
    logger.info("[Pipeline] DSP complete")

    flat_ml = _run_effnet_classifiers(audio_path, list(_EFFNET_CLASSIFIERS))
    flat_ml.update(_run_musicnn_classifiers(audio_path, list(_MUSICNN_CLASSIFIERS)))
    logger.info("[Pipeline] All ML models done")

    try:
        other = extract_other_features(audio_path)
        logger.info("[Pipeline] Other features done")
    except Exception as exc:
        logger.warning("[Pipeline] Other features failed, continuing: %s", exc)
        other = {}

    logger.info("[Pipeline] Full pipeline complete")

    return {
        "metadata": metadata,
        "dsp": dsp,
        "ml": _structure_ml_results(flat_ml),
        "other": other,
    }


def run_single_model(audio_path: Path, model_key: str) -> dict[str, object]:
    """Run one model by key and return its result dict."""
    if model_key not in _EFFNET_CLASSIFIERS and model_key not in _MUSICNN_CLASSIFIERS:
        raise ValueError(f"Unknown model key '{model_key}'. Available: {ALL_MODEL_KEYS}")

    logger.info("[Pipeline] Single-model run: %s on %s", model_key, audio_path.name)
    ensure_models([model_key])

    if model_key in _MUSICNN_CLASSIFIERS:
        return _run_musicnn_classifiers(audio_path, [model_key])
    return _run_effnet_classifiers(audio_path, [model_key])


def save_debug_output(result: dict[str, object], audio_path: Path) -> Path:
    """Write analysis results as JSON to the test_output directory."""
    _TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_UTC")
    output_path = _TEST_OUTPUT_DIR / f"{audio_path.stem}_{timestamp}.json"

    payload = {
        "source_file": str(audio_path),
        "timestamp": timestamp,
        "results": result,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    logger.info("[Pipeline] Debug output saved — %s", output_path)
    return output_path


def _mood_mean(moods: dict, key: str) -> float | None:
    m = moods.get(key)
    return m.get("mean") if isinstance(m, dict) else None


def _mood_ts(moods: dict, key: str) -> list[float] | None:
    m = moods.get(key)
    return m.get("timeseries") if isinstance(m, dict) else None



def _save_to_database(result: dict[str, object], audio_path: Path) -> None:
    """Persist analysis results to the database."""
    from src.db.session import get_session
    from src.db.models import (
        Song, generate_song_id,
        FileMetadata, TrackMetadata, Artist,
        DSPFeatures, MLProfileFeatures, MLMoodFeatures, MLGMBIFeatures,
        OtherFeatures,
        ParentGenre, DetailedGenre, Instrument,
    )

    meta: dict = result.get("metadata") or {}
    dsp: dict = result.get("dsp") or {}
    ml: dict = result.get("ml") or {}

    title = str(meta.get("title") or "")
    artist = str(meta.get("artist") or "")

    if not title or not artist:
        logger.warning("[DB] Skipping %r — metadata extraction returned no %s",
                       audio_path.name, "title" if not title else "artist")
        return

    song_id = generate_song_id(title, artist)
    logger.info("[DB] song_id=%s  title=%r  artist=%r", song_id, title, artist)

    session = get_session()
    try:
        if session.get(Song, song_id):
            logger.warning("[DB] Skipping %r — already in database (id=%s)", title, song_id)
            return

        session.add(Song(id=song_id, title=title, artist=artist))

        session.add(FileMetadata(
            id=song_id,
            filename=meta.get("filename"),
            file_format=meta.get("file_format"),
            duration_seconds=meta.get("duration_seconds"),
            sample_rate_hz=meta.get("sample_rate_hz"),
            bitrate_kbps=meta.get("bitrate_kbps"),
            channels=meta.get("channels"),
        ))

        lastfm: dict = meta.get("lastfm") or {}
        session.add(TrackMetadata(
            id=song_id,
            release_date=meta.get("release_date"),
            playcount=lastfm.get("playcount"),
            listeners=lastfm.get("listeners"),
            mbid=lastfm.get("mbid"),
            url=lastfm.get("url"),
            album_mbid=meta.get("album_mbid"),
            mb_genres=meta.get("genres") or [],
            featured_artists=meta.get("featured_artists") or [],
            similar_tracks=lastfm.get("similar_tracks"),
        ))

        if not session.query(Artist).filter_by(name=artist).first():
            session.add(Artist(
                name=artist,
                artist_playcount=lastfm.get("artist_playcount"),
                artist_listeners=lastfm.get("artist_listeners"),
                artist_bio=lastfm.get("artist_bio"),
                similar_artists=lastfm.get("similar_artists") or [],
            ))

        session.add(DSPFeatures(
            id=song_id,
            bpm=dsp.get("bpm"),
            beat_count=dsp.get("beat_count"),
            beat_confidence=dsp.get("beat_confidence"),
            danceability=dsp.get("danceability"),
            beat_loudness_mean=dsp.get("beat_loudness_mean"),
            onset_rate=dsp.get("onset_rate"),
            key=dsp.get("key"),
            scale=dsp.get("scale"),
            key_strength=dsp.get("key_strength"),
            tuning_frequency_hz=dsp.get("tuning_frequency_hz"),
            tuning_cents_deviation=dsp.get("tuning_cents_deviation"),
            most_common_chord=dsp.get("most_common_chord"),
            chord_strength_mean=dsp.get("chord_strength_mean"),
            chord_change_rate=dsp.get("chord_change_rate"),
            integrated_lufs=dsp.get("integrated_lufs"),
            loudness_range_lu=dsp.get("loudness_range_lu"),
            dynamic_complexity=dsp.get("dynamic_complexity"),
            loudness_db=dsp.get("loudness_db"),
            spectral_centroid_mean=dsp.get("spectral_centroid_mean"),
            spectral_rolloff_mean=dsp.get("spectral_rolloff_mean"),
            spectral_flux_mean=dsp.get("spectral_flux_mean"),
            mfcc_mean=dsp.get("mfcc_mean"),
            zero_crossing_rate=dsp.get("zero_crossing_rate"),
            dissonance=dsp.get("dissonance"),
            loudness_short_term_timeseries=dsp.get("loudness_short_term_timeseries"),
            spectral_centroid_timeseries=dsp.get("spectral_centroid_timeseries"),
            spectral_rolloff_timeseries=dsp.get("spectral_rolloff_timeseries"),
            spectral_flux_timeseries=dsp.get("spectral_flux_timeseries"),
            zero_crossing_rate_timeseries=dsp.get("zero_crossing_rate_timeseries"),
            dissonance_timeseries=dsp.get("dissonance_timeseries"),
        ))

        profile: dict = ml.get("profile") or {}
        approachability: dict = profile.get("approachability") or {}
        engagement: dict = profile.get("engagement") or {}
        voice: dict = profile.get("voice_instrumental") or {}
        gender: dict = profile.get("gender") or {}
        av: dict = profile.get("arousal_valence") or {}
        av_mean: dict = av.get("mean") or {}
        av_ts: list[dict] = av.get("timeseries") or []

        session.add(MLProfileFeatures(
            id=song_id,
            niche_score=approachability.get("niche"),
            mainstream_score=approachability.get("mainstream"),
            approachability_timeseries=approachability.get("timeseries"),
            background_score=engagement.get("background"),
            active_score=engagement.get("active"),
            engagement_timeseries=engagement.get("timeseries"),
            instrumental_score=voice.get("instrumental"),
            vocal_score=voice.get("vocal"),
            voice_timeseries=voice.get("timeseries"),
            female_score=gender.get("female"),
            male_score=gender.get("male"),
            gender_timeseries=gender.get("timeseries"),
            arousal=av_mean.get("arousal"),
            arousal_timeseries=[p["arousal"] for p in av_ts] if av_ts else None,
            valence=av_mean.get("valence"),
            valence_timeseries=[p["valence"] for p in av_ts] if av_ts else None,
        ))

        moods: dict = ml.get("moods") or {}
        session.add(MLMoodFeatures(
            id=song_id,
            happy=_mood_mean(moods, "happy"),
            happy_timeseries=_mood_ts(moods, "happy"),
            sad=_mood_mean(moods, "sad"),
            sad_timeseries=_mood_ts(moods, "sad"),
            aggressive=_mood_mean(moods, "aggressive"),
            aggressive_timeseries=_mood_ts(moods, "aggressive"),
            party=_mood_mean(moods, "party"),
            party_timeseries=_mood_ts(moods, "party"),
            relaxed=_mood_mean(moods, "relaxed"),
            relaxed_timeseries=_mood_ts(moods, "relaxed"),
            acoustic=_mood_mean(moods, "acoustic"),
            acoustic_timeseries=_mood_ts(moods, "acoustic"),
            electronic=_mood_mean(moods, "electronic"),
            electronic_timeseries=_mood_ts(moods, "electronic"),
        ))

        session.add(MLGMBIFeatures(id=song_id))

        other: dict = result.get("other") or {}
        gmbi: dict = other.get("gmbi") or {}
        gmbi_mean: dict = gmbi.get("mean") or {}
        gmbi_frames: dict = gmbi.get("frames") or {}
        tonal_other: dict = other.get("tonal") or {}

        session.add(OtherFeatures(
            id=song_id,
            gmbi_valence=gmbi_mean.get("valence"),
            gmbi_arousal=gmbi_mean.get("arousal"),
            gmbi_authenticity=gmbi_mean.get("authenticity"),
            gmbi_timeliness=gmbi_mean.get("timeliness"),
            gmbi_complexity=gmbi_mean.get("complexity"),
            tonal=tonal_other.get("mean"),
            tonal_timeseries=tonal_other.get("timeseries"),
            hpcp_mean=other.get("hpcp_mean"),
            tristimulus_mean=other.get("tristimulus_mean"),
        ))

        genre_discogs: dict = ml.get("genre_discogs400") or {}
        for g in genre_discogs.get("parent_genre_distribution") or []:
            session.add(ParentGenre(
                id=song_id,
                genre=g["genre"],
                percentage=g["share"],
            ))
        for g in genre_discogs.get("top_10_genres") or []:
            session.add(DetailedGenre(
                id=song_id,
                genre=g["genre"],
                probability=g["probability"],
            ))

        for inst in (ml.get("instrument") or {}).get("top_10") or []:
            session.add(Instrument(
                id=song_id,
                instrument=inst["instrument"],
                probability=inst["probability"],
            ))

        session.commit()
        logger.info("[DB] Saved: %r by %r (%s)", title, artist, song_id)

    except Exception as exc:
        session.rollback()
        logger.error("[DB] Failed to save %r: %s", title, exc)
        raise
    finally:
        session.close()


def _collect_audio_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(
        f for f in path.iterdir()
        if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTENSIONS
    )


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Music Recommender — analysis pipeline")
    parser.add_argument(
        "audio_path",
        type=Path,
        help=f"Audio file or directory. Supported formats: {', '.join(_SUPPORTED_EXTENSIONS)}",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="KEY",
        help=f"Run only this model (single file only). Available keys: {ALL_MODEL_KEYS}",
    )
    parser.add_argument("--save", action="store_true", help="Save results as JSON to test_output/")
    parser.add_argument("--db", action="store_true", help="Save results to the database")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG log level")
    return parser


if __name__ == "__main__":
    args = _build_cli_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="[%(levelname)s] %(message)s",
    )

    import essentia
    essentia.log.infoActive = False
    if not args.debug:
        essentia.log.warningActive = False

    input_path: Path = args.audio_path.resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Path not found: {input_path}")

    audio_files = _collect_audio_files(input_path)
    if not audio_files:
        raise ValueError(f"No supported audio files found in: {input_path}")

    for audio_file in audio_files:
        if audio_file.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported format '{audio_file.suffix}'. Supported: {_SUPPORTED_EXTENSIONS}")

        logger.info("[CLI] Processing: %s", audio_file.name)
        results = run_single_model(audio_file, args.model) if args.model else run_full_pipeline(audio_file)

        if args.db:
            _save_to_database(results, audio_file)
        elif args.save:
            save_debug_output(results, audio_file)
        else:
            print(json.dumps(results, indent=2))
