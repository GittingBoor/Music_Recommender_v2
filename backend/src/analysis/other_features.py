"""
Extraction of additional audio features using the audio_process models.

Extracted features:
  - GMBI (General Music Branding Inventory): valence, arousal, authenticity,
    timeliness, complexity — via Keras Neural Net models (one global prediction
    per song, no per-frame loop).
  - Tonal/Atonal: MusiCNN binary classifier probability of "tonal" class.
  - HPCP mean: 12-bin chroma vector averaged over all frames.
  - Tristimulus mean: 3 tristimulus values averaged over all frames.

Model files are read from ``settings.audio_process_models_dir``
(default: ``src/audio_process/Models`` relative to the backend working dir).
"""
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import essentia.standard as es
from essentia import log as essentia_log

from src.analysis.model_manager import get_cached_algo
from src.core.config import settings

# tensorflow may or may not be importable depending on how essentia-tensorflow
# bundles it. GMBI NN is skipped gracefully if TF is unavailable.
try:
    import tensorflow as tf
    _TF_AVAILABLE = True
except ImportError:
    tf = None  # type: ignore[assignment]
    _TF_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SR_HIGH = 44100
_SR_LOW = 16000
_SR_BPM = 11025
_FRAME_SIZE = 2048
_HOP_SIZE = 1024

_GMBI_DIMS = ("valence", "arousal", "authenticity", "timeliness", "complexity")

# MusiCNN model specs: (filename, output_class_index)
_DL_MODELS: dict[str, tuple[str, int]] = {
    "voice":        ("voice_instrumental-musicnn-msd-2.pb", 1),  # class 1 = voice
    "female":       ("gender-musicnn-msd-2.pb",             0),
    "danceability": ("danceability-musicnn-msd-2.pb",       0),
    "tonal":        ("tonal_atonal-musicnn-msd-2.pb",       0),
}

# MusicExtractor feature paths for GMBI NN input (order is critical — must
# match the z-score training statistics below).
_GMBI_ME_FEATURES = [
    "lowlevel.spectral_centroid.max",    "lowlevel.spectral_centroid.min",
    "lowlevel.spectral_centroid.median", "lowlevel.spectral_centroid.mean",
    "lowlevel.spectral_centroid.stdev",
    "lowlevel.spectral_rolloff.max",     "lowlevel.spectral_rolloff.min",
    "lowlevel.spectral_rolloff.median",  "lowlevel.spectral_rolloff.mean",
    "lowlevel.spectral_rolloff.stdev",
    "lowlevel.spectral_flux.max",        "lowlevel.spectral_flux.min",
    "lowlevel.spectral_flux.median",     "lowlevel.spectral_flux.mean",
    "lowlevel.spectral_flux.stdev",
    "lowlevel.melbands_crest.max",       "lowlevel.melbands_crest.min",
    "lowlevel.melbands_crest.median",    "lowlevel.melbands_crest.mean",
    "lowlevel.melbands_crest.stdev",
    "lowlevel.mfcc.mean",               # expanded to 13 coefficients in code
]

# Z-score parameters from GMBI training dataset (41 values each).
_GMBI_TRAIN_MEAN = [
    4304.467516882324, 261.74677831573484, 1260.9834733947755,
    1359.8331622497558, 635.9399246307373, 10285.1708203125, 80.66337890625,
    1028.98564453125, 1520.3353218078614, 1634.8734796264648,
    0.39592601194083693, 0.000708590870954787, 0.08244796831775457,
    0.10030800342559815, 0.06753226600438356, 33.117014208221434,
    4.244641485500336, 16.40874999732971, 16.9565301448822, 6.161106257915497,
    -656.0196318847657, 118.92494503326417, 10.447095110334455,
    21.845709711566567, 7.000801872124336, 6.495225010318309,
    2.651624589442462, 5.124417172216624, 1.2524997454084457,
    3.597588812500582, 0.1687594781305641, 0.8034831906133332,
    -0.28256157128149645, 0.21183581947386265, 116.5172,
    0.20131734738808008, 0.7907550511702895, 0.44773288787677884,
    0.5534380101077025, 0.7113106577267405, 0.28381864464345935,
]

_GMBI_TRAIN_STDV = [
    1384.9670265215545, 183.2666812918937, 519.4086411089112,
    459.9783269373903, 219.80002148102415, 3148.929935868467,
    43.404677893428534, 680.2361034285709, 710.1270314805328,
    771.7700180865388, 0.11644394110959715, 0.00038664404428150745,
    0.02231384189017726, 0.02255657241125257, 0.02228985539668799,
    3.4861420970718413, 1.2034036918184805, 4.198400071505198,
    3.6131573724981783, 1.536543218984324, 59.07438977889181,
    35.52153093715034, 21.94055368632451, 13.469497097426842,
    9.708297172352388, 9.344183931551497, 8.21357488329068,
    6.930678857265335, 6.273217794176767, 5.53465714477443,
    5.1220975016929025, 4.672487099095496, 4.460216908839947,
    0.052428397131584974, 24.295433812961722, 0.25085396280902705,
    0.2593542864541213, 0.28159425945911337, 0.2810039921374059,
    0.3499780226533626, 0.34698674540391083,
]

# ---------------------------------------------------------------------------
# Lazy NN model cache
# ---------------------------------------------------------------------------
_nn_cache: dict[str, Any] = {}


def _models_dir() -> Path:
    return Path(settings.audio_process_models_dir)


def _get_nn_models() -> dict[str, Any] | None:
    """Load and cache all GMBI Keras NN models (lazy, once per process).

    Returns None if TensorFlow is not importable in this environment.
    """
    if not _TF_AVAILABLE:
        logger.warning(
            "[OtherFeatures] tensorflow not importable — GMBI NN skipped"
        )
        return None
    if _nn_cache:
        return _nn_cache
    nn_dir = _models_dir() / "gmbi_old_nn"
    for dim in _GMBI_DIMS:
        model_path = nn_dir / dim
        if not model_path.exists():
            raise FileNotFoundError(f"GMBI NN model not found: {model_path}")
        logger.info("[OtherFeatures] Loading NN model: %s", dim)
        _nn_cache[dim] = tf.keras.models.load_model(str(model_path))  # type: ignore[union-attr]
    logger.info("[OtherFeatures] All GMBI NN models loaded")
    return _nn_cache


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pool_to_dict(pool) -> dict:
    """Serialize an Essentia pool to a Python dict via a temp JSON file."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        es.YamlOutput(filename=tmp_path, format="json", writeVersion=False)(pool)
        with open(tmp_path, encoding="utf-8") as f:
            return json.load(f)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _run_dl_models(audio_16k: np.ndarray) -> dict[str, dict[str, Any]]:
    """
    Run all 4 MusiCNN classifiers on 16-kHz audio.

    Returns dict keyed by model name with sub-keys:
      ``mean``             — scalar float (predicted class probability mean)
      ``frames``           — list of per-frame floats
      ``both_classes_mean``— list of 2 floats (both class probs, needed for NN)
    """
    models_dir = _models_dir()
    results: dict[str, dict[str, Any]] = {}

    for name, (filename, class_idx) in _DL_MODELS.items():
        model_path = models_dir / filename
        if not model_path.exists():
            raise FileNotFoundError(f"MusiCNN model not found: {model_path}")
        logger.info("[OtherFeatures] Running MusiCNN: %s", name)
        predictor = get_cached_algo(
            (str(model_path),),
            lambda p=model_path: es.TensorflowPredictMusiCNN(graphFilename=str(p)),
        )
        predictions = predictor(audio_16k)
        class_preds = predictions[:, class_idx].astype(float)
        results[name] = {
            "mean":              round(float(np.mean(class_preds)), 8),
            "frames":            np.around(class_preds, decimals=8).tolist(),
            "both_classes_mean": np.around(
                np.mean(predictions, axis=0), decimals=8
            ).tolist(),
        }

    return results


def _extract_gmbi_nn(
    audio_path: Path,
    audio_44k: np.ndarray,
    dl_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Compute GMBI scores via lightweight Keras Neural Net models.

    Runs MusicExtractor once on the full file (one-shot, no chunk loop),
    builds a 41-feature vector, z-score normalises it, and predicts with
    each of the 5 Keras models.

    Returns ``{"mean": {dim: float}, "frames": {}}``.
    """
    logger.info("[OtherFeatures] Running MusicExtractor for GMBI NN")
    _me_key = ("MusicExtractor", _SR_HIGH, _HOP_SIZE, _FRAME_SIZE)
    music_extractor = get_cached_algo(
        _me_key,
        lambda: es.MusicExtractor(
            lowlevelStats=["mean", "stdev", "min", "max", "median"],
            rhythmStats=["mean", "stdev", "min", "max", "median"],
            tonalStats=["mean", "stdev", "min", "max", "median"],
            analysisSampleRate=_SR_HIGH,
            lowlevelHopSize=_HOP_SIZE,
            lowlevelFrameSize=_FRAME_SIZE,
            tonalHopSize=_HOP_SIZE,
            tonalFrameSize=_FRAME_SIZE,
        ),
    )
    stats_pool, _ = music_extractor(str(audio_path))
    stats = _pool_to_dict(stats_pool)

    # Build 41-feature input vector (order must match training)
    feature_vec: list[float] = []

    for feat_path in _GMBI_ME_FEATURES:
        a, b, c = feat_path.split(".")
        if feat_path == "lowlevel.mfcc.mean":
            feature_vec.extend(float(v) for v in stats[a][b][c][:13])
        else:
            feature_vec.append(float(stats[a][b][c]))

    # RMS of the waveform
    feature_vec.append(float(np.sqrt(np.mean(audio_44k ** 2))))

    # BPM via TempoCNN at 11025 Hz
    audio_11k: np.ndarray = es.MonoLoader(
        filename=str(audio_path), sampleRate=_SR_BPM
    )()
    _tempo_pb = str(_models_dir() / "deeptemp-k16-3.pb")
    tempo_cnn = get_cached_algo(
        ("TempoCNN", _tempo_pb),
        lambda p=_tempo_pb: es.TempoCNN(graphFilename=p),
    )
    bpm = float(tempo_cnn(audio_11k)[0])
    feature_vec.append(round(bpm, 2))

    # DL features: voice (both classes), female (both), danceability (both)
    # Order: bpm already appended, then voice→female→danceability (tonal excluded)
    for name in ("voice", "female", "danceability"):
        feature_vec.extend(dl_results[name]["both_classes_mean"])

    # Z-score normalise
    vec = (np.array(feature_vec) - np.array(_GMBI_TRAIN_MEAN)) / np.array(_GMBI_TRAIN_STDV)
    df = pd.DataFrame([vec])

    # Predict with each Keras model
    nn_models = _get_nn_models()
    if nn_models is None:
        return {"mean": {dim: None for dim in _GMBI_DIMS}, "frames": {}}

    means: dict[str, float] = {}
    for dim in _GMBI_DIMS:
        pred = nn_models[dim].predict(df, verbose=0).flatten()
        means[dim] = float(pred[0])
        logger.info("[OtherFeatures] GMBI NN %s = %.4f", dim, means[dim])

    return {"mean": means, "frames": {}}


def _extract_hpcp_tristimulus(audio_44k: np.ndarray) -> dict[str, Any]:
    """Compute per-frame HPCP (12-bin chroma) and Tristimulus, return means."""
    window_algo = es.Windowing(type="hann")
    spectrum_algo = es.Spectrum(size=_FRAME_SIZE)
    peaks_algo = es.SpectralPeaks()
    hpcp_algo = es.HPCP()
    harmonic_peaks_algo = es.HarmonicPeaks()
    tristimulus_algo = es.Tristimulus()

    hpcps: list[np.ndarray] = []
    tristimuli: list[np.ndarray] = []

    for frame in es.FrameGenerator(
        audio_44k, frameSize=_FRAME_SIZE, hopSize=_HOP_SIZE, startFromZero=True
    ):
        windowed = window_algo(frame)
        spectrum = spectrum_algo(windowed)
        freqs, mags = peaks_algo(spectrum)

        if len(freqs) > 0:
            hpcps.append(hpcp_algo(freqs, mags))
            try:
                h_freqs, h_mags = harmonic_peaks_algo(freqs, mags, freqs[0])
                tristimuli.append(tristimulus_algo(h_freqs, h_mags))
            except Exception:
                pass

    hpcp_mean = (
        [round(float(v), 6) for v in np.mean(hpcps, axis=0)]
        if hpcps else None
    )
    tristimulus_mean = (
        [round(float(v), 6) for v in np.mean(tristimuli, axis=0)]
        if tristimuli else None
    )

    return {"hpcp_mean": hpcp_mean, "tristimulus_mean": tristimulus_mean}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_other_features(audio_path: Path) -> dict[str, Any]:
    """
    Run the full other-features extraction pipeline on *audio_path*.

    Returns
    -------
    dict with keys:
      ``gmbi``             — ``{"mean": {dim: float}, "frames": {}}``
      ``tonal``            — ``{"mean": float, "timeseries": [float]}``
      ``hpcp_mean``        — list of 12 floats
      ``tristimulus_mean`` — list of 3 floats
    """
    logger.info("[OtherFeatures] Starting — %s", audio_path.name)
    essentia_log.infoActive = False

    logger.info("[OtherFeatures] Loading audio")
    audio_44k: np.ndarray = es.MonoLoader(
        filename=str(audio_path), sampleRate=_SR_HIGH
    )()
    audio_16k: np.ndarray = es.MonoLoader(
        filename=str(audio_path), sampleRate=_SR_LOW
    )()

    logger.info("[OtherFeatures] Running MusiCNN classifiers")
    dl_results = _run_dl_models(audio_16k)

    tonal_result = {
        "mean":       dl_results["tonal"]["mean"],
        "timeseries": dl_results["tonal"]["frames"],
    }
    logger.info("[OtherFeatures] Tonal/Atonal done (mean=%.4f)", tonal_result["mean"])

    logger.info("[OtherFeatures] Running GMBI Neural Net")
    gmbi = _extract_gmbi_nn(audio_path, audio_44k, dl_results)
    logger.info(
        "[OtherFeatures] GMBI done — valence=%.4f arousal=%.4f",
        gmbi["mean"].get("valence", 0),
        gmbi["mean"].get("arousal", 0),
    )

    logger.info("[OtherFeatures] Computing HPCP / Tristimulus")
    harmony = _extract_hpcp_tristimulus(audio_44k)
    logger.info("[OtherFeatures] Complete — %s", audio_path.name)

    return {
        "gmbi":             gmbi,
        "tonal":            tonal_result,
        "hpcp_mean":        harmony["hpcp_mean"],
        "tristimulus_mean": harmony["tristimulus_mean"],
    }
