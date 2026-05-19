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


def _load_audio_44k(audio_path: Path) -> np.ndarray:
    """Load audio as 44.1 kHz mono for DSP processing."""
    logger.info("[DSP] Loading audio: %s at %d Hz", audio_path.name, _SAMPLE_RATE)
    return es.MonoLoader(filename=str(audio_path), sampleRate=_SAMPLE_RATE)()


def _iter_frames(audio: np.ndarray) -> Iterator[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Yield (raw_frame, windowed_frame, spectrum) for each analysis frame."""
    window = es.Windowing(type="hann")
    spectrum_algo = es.Spectrum(size=_FRAME_SIZE)
    for frame in es.FrameGenerator(audio, frameSize=_FRAME_SIZE, hopSize=_HOP_SIZE, startFromZero=True):
        windowed = window(frame)
        yield frame, windowed, spectrum_algo(windowed)


def _run_rhythm_extractor(audio: np.ndarray) -> tuple[dict[str, object], np.ndarray]:
    """Run RhythmExtractor2013 and return (stats, raw_beats_array)."""
    bpm, beats, confidence, _, _ = es.RhythmExtractor2013()(audio)
    stats = {
        "bpm": round(float(bpm), 2),
        "beat_count": int(len(beats)),
        "beat_confidence": round(float(confidence), 4),
    }
    return stats, beats


def extract_bpm_and_beats(audio: np.ndarray) -> dict[str, object]:
    """Extract BPM, beat count, and beat confidence."""
    stats, _ = _run_rhythm_extractor(audio)
    logger.debug("[DSP] BPM = %.1f", stats["bpm"])
    return stats


def extract_danceability(audio: np.ndarray) -> float:
    """Extract danceability score (0–3, higher = more danceable)."""
    danceability, _ = es.Danceability()(audio)
    return round(float(danceability), 4)


def extract_beat_loudness(audio: np.ndarray, beats: np.ndarray) -> float:
    """Extract mean loudness at beat positions (requires beats from RhythmExtractor)."""
    if len(beats) == 0:
        return 0.0
    loudness, _ = es.BeatsLoudness(beats=beats)(audio)
    return round(float(np.mean(loudness)), 4)


def extract_onset_rate(audio: np.ndarray) -> float:
    """Extract onset rate in onsets per second."""
    _, onset_rate = es.OnsetRate()(audio)
    return round(float(onset_rate), 4)


def extract_key(audio: np.ndarray) -> dict[str, object]:
    """Extract musical key, scale (major/minor), and key detection strength."""
    key, scale, strength = es.KeyExtractor()(audio)
    logger.debug("[DSP] Key = %s %s (strength: %.3f)", key, scale, strength)
    return {
        "key": key,
        "scale": scale,
        "key_strength": round(float(strength), 4),
    }


def extract_tuning(audio: np.ndarray) -> dict[str, float]:
    """Extract tuning frequency and deviation from 440 Hz in cents via spectral peaks."""
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


def extract_loudness_ebur128(audio: np.ndarray) -> dict[str, float]:
    """Extract integrated loudness (LUFS) and loudness range via EBU R128."""
    audio_stereo = np.column_stack([audio, audio]).astype(np.float32)
    # Output order: momentaryLoudness (vector), shortTermLoudness (vector), integratedLoudness, loudnessRange
    _, _, integrated, loudness_range = es.LoudnessEBUR128(sampleRate=_SAMPLE_RATE)(audio_stereo)
    return {
        "integrated_lufs": round(float(integrated), 4),
        "loudness_range_lu": round(float(loudness_range), 4),
    }


def extract_dynamic_complexity(audio: np.ndarray) -> dict[str, float]:
    """Extract dynamic complexity score and mean loudness in dB."""
    complexity, loudness = es.DynamicComplexity()(audio)
    return {
        "dynamic_complexity": round(float(complexity), 4),
        "loudness_db": round(float(loudness), 4),
    }


def extract_spectral_features(audio: np.ndarray) -> dict[str, float]:
    """Extract mean spectral centroid, rolloff, and flux across frames."""
    centroid_algo = es.SpectralCentroidTime()
    rolloff_algo = es.RollOff()
    flux_algo = es.Flux()

    centroids, rolloffs, fluxes = [], [], []
    for frame, windowed, spectrum in _iter_frames(audio):
        centroids.append(centroid_algo(windowed))
        rolloffs.append(rolloff_algo(spectrum))
        fluxes.append(flux_algo(spectrum))

    return {
        "spectral_centroid_mean": round(float(np.mean(centroids)), 4),
        "spectral_rolloff_mean": round(float(np.mean(rolloffs)), 4),
        "spectral_flux_mean": round(float(np.mean(fluxes)), 4),
    }


def extract_mfcc(audio: np.ndarray) -> list[float]:
    """Extract mean MFCC across all frames (13 coefficients)."""
    mfcc_algo = es.MFCC(numberCoefficients=13)
    coeffs_list = []
    for _, _, spectrum in _iter_frames(audio):
        _, mfcc_coeffs = mfcc_algo(spectrum)
        coeffs_list.append(mfcc_coeffs)
    mean_coeffs = np.mean(coeffs_list, axis=0)
    return [round(float(c), 4) for c in mean_coeffs]


def extract_zero_crossing_rate(audio: np.ndarray) -> float:
    """Extract mean zero crossing rate across frames."""
    zcr_algo = es.ZeroCrossingRate()
    rates = [zcr_algo(frame) for frame, _, _ in _iter_frames(audio)]
    return round(float(np.mean(rates)), 4)


def extract_dissonance(audio: np.ndarray) -> float:
    """Extract mean dissonance across frames."""
    peaks_algo = es.SpectralPeaks()
    dissonance_algo = es.Dissonance()
    values = []
    for _, _, spectrum in _iter_frames(audio):
        freqs, mags = peaks_algo(spectrum)
        values.append(dissonance_algo(freqs, mags))
    return round(float(np.mean(values)), 4)


def extract_chords(audio: np.ndarray) -> dict[str, object]:
    """Extract most common chord, mean strength, and chord change rate."""
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
    """Run all DSP feature extractors on an audio file and return a flat feature dict."""
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

    logger.info("[DSP] Extracting spectral features")
    result.update(extract_spectral_features(audio))
    result["mfcc_mean"] = extract_mfcc(audio)
    result["zero_crossing_rate"] = extract_zero_crossing_rate(audio)
    result["dissonance"] = extract_dissonance(audio)
    logger.info("[DSP] Spectral features done")

    logger.info("[DSP] DSP extraction complete — %d features", len(result))
    return result
