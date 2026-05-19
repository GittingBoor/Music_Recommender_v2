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
    "instrument": predict_instrument,  # last — will appear at end of JSON
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

    metadata = extract_all_metadata(audio_path, lastfm_api_key=settings.lastfm_api_key)
    logger.info("[Pipeline] Metadata complete")

    dsp = extract_all_dsp_features(audio_path)
    logger.info("[Pipeline] DSP complete")

    flat_ml = _run_effnet_classifiers(audio_path, list(_EFFNET_CLASSIFIERS))
    flat_ml.update(_run_musicnn_classifiers(audio_path, list(_MUSICNN_CLASSIFIERS)))
    logger.info("[Pipeline] All ML models done")

    logger.info("[Pipeline] Full pipeline complete")

    # TODO: replace save_debug_output with _save_to_database once DB layer is ready
    return {
        "metadata": metadata,
        "dsp": dsp,
        "ml": _structure_ml_results(flat_ml),
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


def _save_to_database(result: dict[str, object], audio_path: Path) -> None:
    """Persist analysis results to the database. Not yet implemented."""
    # TODO: create Track + AnalysisResult ORM records via SQLAlchemy session
    logger.debug("[Pipeline] _save_to_database not yet implemented — skipping")


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Music Recommender — analysis pipeline")
    parser.add_argument(
        "audio_file",
        type=Path,
        help=f"Path to audio file. Supported formats: {', '.join(_SUPPORTED_EXTENSIONS)}",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="KEY",
        help=f"Run only this model. Available keys: {ALL_MODEL_KEYS}",
    )
    parser.add_argument("--save", action="store_true", help="Save results to test_output/")
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

    audio_path: Path = args.audio_file.resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if audio_path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported format '{audio_path.suffix}'. Supported: {_SUPPORTED_EXTENSIONS}")

    results = run_single_model(audio_path, args.model) if args.model else run_full_pipeline(audio_path)

    if args.save:
        save_debug_output(results, audio_path)
    else:
        print(json.dumps(results, indent=2))
