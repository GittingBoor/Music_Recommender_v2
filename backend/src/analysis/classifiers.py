import logging
from pathlib import Path

import numpy as np
import essentia.standard as es

from src.analysis.model_manager import get_manager

logger = logging.getLogger(__name__)

# TF1-style models use "model/Placeholder" / "model/Softmax" (default).
# TF2 SavedModel exports use "serving_default_model_Placeholder" / "PartitionedCall".
_TF1_INPUT = "model/Placeholder"
_TF2_INPUT = "serving_default_model_Placeholder"
_TF2_OUTPUT = "PartitionedCall"

# (input_layer, output_layer) — only entries that differ from TF1 defaults.
# Mood/2-class models are TF1. Multi-label and v2 models are TF2.
_LAYER_OVERRIDES: dict[str, tuple[str, str]] = {
    "genre_discogs400": (_TF2_INPUT, _TF2_OUTPUT),  # confirmed TF2
}


def _run_classifier(model_key: str, embedding: np.ndarray, output_layer: str) -> np.ndarray:
    """Run a TensorflowPredict2D model and return mean predictions across patches."""
    path = get_manager().get_path(model_key)
    input_layer, out = _LAYER_OVERRIDES.get(model_key, (_TF1_INPUT, output_layer))
    model = es.TensorflowPredict2D(
        graphFilename=str(path),
        input=input_layer,
        output=out,
    )
    predictions: np.ndarray = model(embedding)
    return np.mean(predictions, axis=0)


def _log(model_key: str, value: object) -> None:
    logger.debug("[Classifier] %s = %s", model_key, value)


def predict_mood_happy(embedding: np.ndarray) -> float:
    """Return probability of happy mood (0–1)."""
    result = _run_classifier("mood_happy", embedding, "model/Softmax")
    prob = float(result[1])
    _log("mood_happy", f"{prob:.3f}")
    return prob


def predict_mood_sad(embedding: np.ndarray) -> float:
    """Return probability of sad mood (0–1)."""
    result = _run_classifier("mood_sad", embedding, "model/Softmax")
    prob = float(result[1])
    _log("mood_sad", f"{prob:.3f}")
    return prob


def predict_mood_aggressive(embedding: np.ndarray) -> float:
    """Return probability of aggressive mood (0–1)."""
    result = _run_classifier("mood_aggressive", embedding, "model/Softmax")
    prob = float(result[1])
    _log("mood_aggressive", f"{prob:.3f}")
    return prob


def predict_mood_party(embedding: np.ndarray) -> float:
    """Return probability of party mood (0–1)."""
    result = _run_classifier("mood_party", embedding, "model/Softmax")
    prob = float(result[1])
    _log("mood_party", f"{prob:.3f}")
    return prob


def predict_mood_relaxed(embedding: np.ndarray) -> float:
    """Return probability of relaxed mood (0–1)."""
    result = _run_classifier("mood_relaxed", embedding, "model/Softmax")
    prob = float(result[1])
    _log("mood_relaxed", f"{prob:.3f}")
    return prob


def predict_mood_acoustic(embedding: np.ndarray) -> float:
    """Return probability of acoustic character (0–1)."""
    result = _run_classifier("mood_acoustic", embedding, "model/Softmax")
    prob = float(result[1])
    _log("mood_acoustic", f"{prob:.3f}")
    return prob


def predict_mood_electronic(embedding: np.ndarray) -> float:
    """Return probability of electronic character (0–1)."""
    result = _run_classifier("mood_electronic", embedding, "model/Softmax")
    prob = float(result[1])
    _log("mood_electronic", f"{prob:.3f}")
    return prob


def predict_arousal_valence(embedding: np.ndarray) -> dict[str, float]:
    """Return arousal and valence on a 1–9 scale from MusiCNN embedding."""
    # DEAM is a regression model — output layer is Identity, not Softmax
    result = _run_classifier("arousal_valence", embedding, "model/Identity")
    av = {"arousal": float(result[0]), "valence": float(result[1])}
    _log("arousal_valence", av)
    return av


def predict_genre_discogs400(embedding: np.ndarray) -> dict[str, object]:
    """Return top-10 genre predictions out of 400 Discogs styles (multi-label)."""
    result = _run_classifier("genre_discogs400", embedding, "model/Sigmoid")
    top_indices: list[int] = np.argsort(result)[::-1][:10].tolist()
    top = [{"index": int(i), "probability": float(result[i])} for i in top_indices]
    _log("genre_discogs400", f"top={top[0]}")
    return {"top_10": top, "all_probabilities": result.tolist()}


def predict_approachability(embedding: np.ndarray) -> dict[str, float]:
    """Return niche vs mainstream probabilities."""
    result = _run_classifier("approachability", embedding, "model/Softmax")
    av = {"niche": float(result[0]), "mainstream": float(result[1])}
    _log("approachability", av)
    return av


def predict_engagement(embedding: np.ndarray) -> dict[str, float]:
    """Return background vs active listening probabilities."""
    result = _run_classifier("engagement", embedding, "model/Softmax")
    av = {"background": float(result[0]), "active": float(result[1])}
    _log("engagement", av)
    return av


def predict_instrument(embedding: np.ndarray) -> dict[str, object]:
    """Return top-10 instrument predictions out of 40 classes (multi-label)."""
    result = _run_classifier("instrument", embedding, "model/Sigmoid")
    top_indices: list[int] = np.argsort(result)[::-1][:10].tolist()
    top = [{"index": int(i), "probability": float(result[i])} for i in top_indices]
    _log("instrument", f"top={top[0]}")
    return {"top_10": top, "all_probabilities": result.tolist()}


def predict_voice_instrumental(embedding: np.ndarray) -> dict[str, float]:
    """Return instrumental vs vocal probabilities."""
    result = _run_classifier("voice_instrumental", embedding, "model/Softmax")
    av = {"instrumental": float(result[0]), "vocal": float(result[1])}
    _log("voice_instrumental", av)
    return av


def predict_gender(embedding: np.ndarray) -> dict[str, float]:
    """Return female vs male voice probabilities."""
    result = _run_classifier("gender", embedding, "model/Softmax")
    av = {"female": float(result[0]), "male": float(result[1])}
    _log("gender", av)
    return av
