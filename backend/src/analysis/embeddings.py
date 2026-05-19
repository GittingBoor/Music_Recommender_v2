import logging
from pathlib import Path

import numpy as np
import essentia.standard as es

from src.analysis.model_manager import get_manager

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16000

_EFFNET_OUTPUT_LAYER = "PartitionedCall:1"
_MUSICNN_OUTPUT_LAYER = "model/dense/BiasAdd"


def load_audio_mono(wav_path: Path, sample_rate: int = _SAMPLE_RATE) -> np.ndarray:
    """Load a WAV file as mono audio at the given sample rate."""
    logger.info("[Embedding] Loading audio: %s at %d Hz", wav_path.name, sample_rate)
    return es.MonoLoader(filename=str(wav_path), sampleRate=sample_rate)()


def extract_effnet_embedding(wav_path: Path) -> np.ndarray:
    """Extract Discogs-EffNet embeddings (shape: n_patches x 1280) from a WAV file."""
    manager = get_manager()
    manager.ensure_key("effnet_embedding")

    audio = load_audio_mono(wav_path)
    model_path = manager.get_path("effnet_embedding")

    logger.info("[Embedding] Computing EffNet embedding")
    embedder = es.TensorflowPredictEffnetDiscogs(
        graphFilename=str(model_path),
        output=_EFFNET_OUTPUT_LAYER,
    )
    embeddings: np.ndarray = embedder(audio)
    logger.info("[Embedding] EffNet complete — shape %s", str(embeddings.shape))
    return embeddings


def extract_musicnn_embedding(wav_path: Path) -> np.ndarray:
    """Extract MSD-MusiCNN embeddings (shape: n_patches x 200) from a WAV file."""
    manager = get_manager()
    manager.ensure_key("musicnn_embedding")

    audio = load_audio_mono(wav_path)
    model_path = manager.get_path("musicnn_embedding")

    logger.info("[Embedding] Computing MusiCNN embedding")
    embedder = es.TensorflowPredictMusiCNN(
        graphFilename=str(model_path),
        output=_MUSICNN_OUTPUT_LAYER,
    )
    embeddings: np.ndarray = embedder(audio)
    logger.info("[Embedding] MusiCNN complete — shape %s", str(embeddings.shape))
    return embeddings
