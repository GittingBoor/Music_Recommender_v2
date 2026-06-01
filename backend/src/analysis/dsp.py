import logging
from collections import Counter
from pathlib import Path
from typing import Iterator

import numpy as np
import essentia.standard as es

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 44100
_FRAME_SIZE = 2048
_HOP_SIZE = 1024
_FRAMES_PER_SECOND = _SAMPLE_RATE / _HOP_SIZE  # ~43 frames/sec


def _load_audio_44k(audio_path: Path) -> np.ndarray:
    logger.info("[DSP] Loading audio: %s at %d Hz", audio_path.name, _SAMPLE_RATE)
    return es.MonoLoader(filename=str(audio_path), sampleRate=_SAMPLE_RATE)()


def _iter_frames(audio: np.ndarray) -> Iterator[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Yield (raw_frame, windowed_frame, spectrum) for each analysis frame."""
    window = es.Windowing(type="hann")
    spectrum_algo = es.Spectrum(size=_FRAME_SIZE)
    for frame in es.FrameGenerator(audio, frameSize=_FRAME_SIZE, hopSize=_HOP_SIZE, startFromZero=True):
        windowed = window(frame)
        yield frame, windowed, spectrum_algo(windowed)


def _frames_to_seconds(values: list[float]) -> list[float]:
    """Group frame-level values into per-second means."""
    result = []
    i = 0
    n = len(values)
    step = int(_FRAMES_PER_SECOND)
    while i < n:
        chunk = values[i:i + step]
        result.append(round(float(np.mean(chunk)), 4))
        i += step
    return result


def _run_rhythm_extractor(audio: np.ndarray) -> tuple[dict[str, object], np.ndarray]:
    bpm, beats, confidence, _, _ = es.RhythmExtractor2013()(audio)
    stats = {
        "bpm": round(float(bpm), 2),
        "beat_count": int(len(beats)),
        "beat_confidence": round(float(confidence), 4),
    }
    return stats, beats


def extract_bpm_and_beats(audio: np.ndarray) -> dict[str, object]:
    stats, _ = _run_rhythm_extractor(audio)
    logger.debug("[DSP] BPM = %.1f", stats["bpm"])
    return stats


def extract_danceability(audio: np.ndarray) -> float:
    danceability, _ = es.Danceability()(audio)
    return round(float(danceability), 4)


def extract_beat_loudness(audio: np.ndarray, beats: np.ndarray) -> float:
    if len(beats) == 0:
        return 0.0
    loudness, _ = es.BeatsLoudness(beats=beats)(audio)
    return round(float(np.mean(loudness)), 4)


def extract_onset_rate(audio: np.ndarray) -> float:
    _, onset_rate = es.OnsetRate()(audio)
    return round(float(onset_rate), 4)


def extract_key(audio: np.ndarray) -> dict[str, object]:
    key, scale, strength = es.KeyExtractor()(audio)
    logger.debug("[DSP] Key = %s %s (strength: %.3f)", key, scale, strength)
    return {
        "key": key,
        "scale": scale,
        "key_strength": round(float(strength), 4),
    }


def extract_tuning(audio: np.ndarray) -> dict[str, float]:
    peaks_algo = es.SpectralPeaks()
    tuning_algo = es.TuningFrequency()
    freq, cents = 440.0, 0.0
    for _, _, spectrum in _iter_frames(audio):
        freqs, mags = peaks_algo(spectrum)
        if len(freqs) > 0:
            freq, cents = tuning_algo(freqs, mags)
    return {
        "tuning_frequency_hz": round(float(freq), 4),
        "tuning_cents_deviation": round(float(cents), 4),
    }


def extract_loudness_ebur128(audio: np.ndarray) -> dict[str, object]:
    audio_stereo = np.column_stack([audio, audio]).astype(np.float32)
    momentary, short_term, integrated, loudness_range = es.LoudnessEBUR128(sampleRate=_SAMPLE_RATE)(audio_stereo)
    return {
        "integrated_lufs": round(float(integrated), 4),
        "loudness_range_lu": round(float(loudness_range), 4),
        # short_term is measured every ~3s — good resolution for loudness graphs
        "loudness_short_term_timeseries": [round(float(v), 4) for v in short_term],
    }


def extract_dynamic_complexity(audio: np.ndarray) -> dict[str, float]:
    complexity, loudness = es.DynamicComplexity()(audio)
    return {
        "dynamic_complexity": round(float(complexity), 4),
        "loudness_db": round(float(loudness), 4),
    }


def extract_chords(audio: np.ndarray) -> dict[str, object]:
    peaks_algo = es.SpectralPeaks()
    hpcp_algo = es.HPCP()

    hpcps = []
    for _, _, spectrum in _iter_frames(audio):
        freqs, mags = peaks_algo(spectrum)
        hpcps.append(hpcp_algo(freqs, mags))

    chords, strengths = es.ChordsDetection()(np.array(hpcps))
    most_common = Counter(chords).most_common(1)[0][0]
    changes = sum(1 for i in range(1, len(chords)) if chords[i] != chords[i - 1])
    change_rate = round(changes / len(chords), 4) if len(chords) > 0 else 0.0

    return {
        "most_common_chord": most_common,
        "chord_strength_mean": round(float(np.mean(strengths)), 4),
        "chord_change_rate": change_rate,
    }


def extract_all_dsp_features(audio_path: Path) -> dict[str, object]:
    logger.info("[DSP] Starting DSP extraction — %s", audio_path.name)
    audio = _load_audio_44k(audio_path)

    logger.info("[DSP] Extracting rhythm features")
    rhythm_stats, beats = _run_rhythm_extractor(audio)
    result: dict[str, object] = {
        **rhythm_stats,
        "danceability": extract_danceability(audio),
        "beat_loudness_mean": extract_beat_loudness(audio, beats),
        "onset_rate": extract_onset_rate(audio),
    }
    logger.info("[DSP] Rhythm features done")

    logger.info("[DSP] Extracting tonal features")
    result.update(extract_key(audio))
    result.update(extract_tuning(audio))
    result.update(extract_chords(audio))
    logger.info("[DSP] Tonal features done")

    logger.info("[DSP] Extracting loudness features")
    result.update(extract_loudness_ebur128(audio))
    result.update(extract_dynamic_complexity(audio))
    logger.info("[DSP] Loudness features done")

    logger.info("[DSP] Extracting spectral features (single frame pass)")
    centroid_algo = es.SpectralCentroidTime()
    rolloff_algo = es.RollOff()
    flux_algo = es.Flux()
    peaks_algo = es.SpectralPeaks()
    dissonance_algo = es.Dissonance()
    zcr_algo = es.ZeroCrossingRate()
    mfcc_algo = es.MFCC(numberCoefficients=13)

    centroids: list[float] = []
    rolloffs: list[float] = []
    fluxes: list[float] = []
    dissonances: list[float] = []
    zcrs: list[float] = []
    mfcc_frames: list[np.ndarray] = []

    for frame, windowed, spectrum in _iter_frames(audio):
        centroids.append(float(centroid_algo(windowed)))
        rolloffs.append(float(rolloff_algo(spectrum)))
        fluxes.append(float(flux_algo(spectrum)))
        zcrs.append(float(zcr_algo(frame)))
        freqs, mags = peaks_algo(spectrum)
        dissonances.append(float(dissonance_algo(freqs, mags)))
        _, mfcc_coeffs = mfcc_algo(spectrum)
        mfcc_frames.append(mfcc_coeffs)

    result.update({
        "spectral_centroid_mean": round(float(np.mean(centroids)), 4),
        "spectral_rolloff_mean": round(float(np.mean(rolloffs)), 4),
        "spectral_flux_mean": round(float(np.mean(fluxes)), 4),
        "mfcc_mean": [round(float(c), 4) for c in np.mean(mfcc_frames, axis=0)],
        "zero_crossing_rate": round(float(np.mean(zcrs)), 4),
        "dissonance": round(float(np.mean(dissonances)), 4),
        "spectral_centroid_timeseries": _frames_to_seconds(centroids),
        "spectral_rolloff_timeseries": _frames_to_seconds(rolloffs),
        "spectral_flux_timeseries": _frames_to_seconds(fluxes),
        "zero_crossing_rate_timeseries": _frames_to_seconds(zcrs),
        "dissonance_timeseries": _frames_to_seconds(dissonances),
    })
    logger.info("[DSP] Spectral features done")

    logger.info("[DSP] DSP extraction complete — %d features", len(result))
    return result
