import logging
from pathlib import Path

import numpy as np
import essentia.standard as es

from src.analysis.model_manager import get_manager

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16000

_EFFNET_OUTPUT_LAYER = "PartitionedCall:1"
_MUSICNN_OUTPUT_LAYER = "model/dense/BiasAdd"

# Minimum audio duration (seconds) required to produce at least one embedding patch.
# EffNet uses ~1s patches at 16kHz; MusiCNN uses similar windows.
_MIN_DURATION_SECONDS = 3.0


def load_audio_mono(audio_path: Path, sample_rate: int = _SAMPLE_RATE) -> np.ndarray:
    logger.info("[Embedding] Loading audio: %s at %d Hz", audio_path.name, sample_rate)
    audio = es.MonoLoader(filename=str(audio_path), sampleRate=sample_rate)()
    duration = len(audio) / sample_rate
    if duration < _MIN_DURATION_SECONDS:
        raise ValueError(
            f"Audio too short ({duration:.2f}s < {_MIN_DURATION_SECONDS}s minimum) — "
            "cannot produce ML embeddings."
        )
    return audio


def _to_2d(raw: object, label: str) -> np.ndarray:
    """Convert Essentia's output (list or ndarray) to a 2D numpy array."""
    arr = np.array(raw)
    if arr.ndim == 0 or arr.size == 0:
        raise ValueError(f"{label} produced an empty embedding — audio too short.")
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    elif arr.ndim == 3:
        arr = arr.squeeze(0)
    if arr.ndim != 2 or arr.shape[1] == 0:
        raise ValueError(f"{label} embedding has unexpected shape {arr.shape}.")
    return arr


def extract_effnet_embedding(audio_path: Path) -> np.ndarray:
    """Extract Discogs-EffNet embeddings (shape: n_patches x 1280)."""
    manager = get_manager()
    manager.ensure_key("effnet_embedding")

    audio = load_audio_mono(audio_path)
    model_path = manager.get_path("effnet_embedding")

    logger.info("[Embedding] Computing EffNet embedding")
    embedder = es.TensorflowPredictEffnetDiscogs(
        graphFilename=str(model_path),
        output=_EFFNET_OUTPUT_LAYER,
    )
    embeddings = _to_2d(embedder(audio), "EffNet")
    logger.info("[Embedding] EffNet complete — shape %s", str(embeddings.shape))
    return embeddings


def extract_musicnn_embedding(audio_path: Path) -> np.ndarray:
    """Extract MSD-MusiCNN embeddings (shape: n_patches x 200)."""
    manager = get_manager()
    manager.ensure_key("musicnn_embedding")

    audio = load_audio_mono(audio_path)
    model_path = manager.get_path("musicnn_embedding")

    logger.info("[Embedding] Computing MusiCNN embedding")
    embedder = es.TensorflowPredictMusiCNN(
        graphFilename=str(model_path),
        output=_MUSICNN_OUTPUT_LAYER,
    )
    embeddings = _to_2d(embedder(audio), "MusiCNN")
    logger.info("[Embedding] MusiCNN complete — shape %s", str(embeddings.shape))
    return embeddings
