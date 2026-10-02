import type { Song } from "../../types/song";

export interface AxisStats {
  min: number;
  max: number;
}

export type AxisStatsMap = Record<string, AxisStats>;

export interface RadarAxis {
  key: string;
  label: string;
  /** FIELD_DESCRIPTIONS key ("<table>.<column>") explaining the value. */
  field: string;
  get: (s: Song) => number | null;
  /** Returns a normalised 0–1 value for filtering. stats is provided but may be ignored. */
  norm: (v: number, stats: AxisStats) => number;
  /** How a slider position maps onto the raw value. */
  scaleHint: string;
}

function clamp(v: number, lo = 0, hi = 1): number {
  return Math.max(lo, Math.min(hi, v));
}

function minMax(v: number, stats: AxisStats): number {
  if (stats.max === stats.min) return 0.5;
  return clamp((v - stats.min) / (stats.max - stats.min));
}

// Normalisations, each with the explanation shown in the slider tooltip.
const PROBABILITY = {
  norm: (v: number) => clamp(v),
  scaleHint: "Slider = the probability itself (50% = 0.50).",
};
const LIBRARY_RANGE = {
  norm: minMax,
  scaleHint: "Slider runs from the lowest (0%) to the highest (100%) value in your library.",
};
/** GMBI scores are z-scores; ±2 covers practically all songs. */
const Z_SCORE = {
  norm: (v: number) => clamp((v + 2) / 4),
  scaleHint: "Slider maps the score from −2 (0%) over 0 (50%) to +2 (100%).",
};

// ── Moods ──────────────────────────────────────────────────────────────────
export const MOOD_AXES: RadarAxis[] = [
  { key: "happy",      label: "Happy",      field: "ml_mood_features.happy",      get: s => s.ml_moods?.happy      ?? null, ...PROBABILITY },
  { key: "sad",        label: "Sad",        field: "ml_mood_features.sad",        get: s => s.ml_moods?.sad        ?? null, ...PROBABILITY },
  { key: "aggressive", label: "Aggressive", field: "ml_mood_features.aggressive", get: s => s.ml_moods?.aggressive ?? null, ...PROBABILITY },
  { key: "party",      label: "Party",      field: "ml_mood_features.party",      get: s => s.ml_moods?.party      ?? null, ...PROBABILITY },
  { key: "relaxed",    label: "Relaxed",    field: "ml_mood_features.relaxed",    get: s => s.ml_moods?.relaxed    ?? null, ...PROBABILITY },
  { key: "acoustic",   label: "Acoustic",   field: "ml_mood_features.acoustic",   get: s => s.ml_moods?.acoustic   ?? null, ...PROBABILITY },
  { key: "electronic", label: "Electronic", field: "ml_mood_features.electronic", get: s => s.ml_moods?.electronic ?? null, ...PROBABILITY },
];

// ── DSP features (curated subset, readable in a radar) ─────────────────────
// All on the library range: even the 0–1 ones (danceability, key strength) only
// use a narrow band of it, and beat confidence goes up to ~5.3.
export const DSP_AXES: RadarAxis[] = [
  { key: "danceability",          label: "Dance",       field: "dsp_features.danceability",           get: s => s.dsp_features?.danceability          ?? null, ...LIBRARY_RANGE },
  { key: "beat_confidence",       label: "Beat Conf.",  field: "dsp_features.beat_confidence",        get: s => s.dsp_features?.beat_confidence       ?? null, ...LIBRARY_RANGE },
  { key: "key_strength",          label: "Key Str.",    field: "dsp_features.key_strength",           get: s => s.dsp_features?.key_strength          ?? null, ...LIBRARY_RANGE },
  { key: "dynamic_complexity",    label: "Dyn. Compl.", field: "dsp_features.dynamic_complexity",     get: s => s.dsp_features?.dynamic_complexity    ?? null, ...LIBRARY_RANGE },
  { key: "onset_rate",            label: "Onset Rate",  field: "dsp_features.onset_rate",             get: s => s.dsp_features?.onset_rate            ?? null, ...LIBRARY_RANGE },
  { key: "dissonance",            label: "Dissonance",  field: "dsp_features.dissonance",             get: s => s.dsp_features?.dissonance            ?? null, ...LIBRARY_RANGE },
  { key: "bpm",                   label: "BPM",         field: "dsp_features.bpm",                    get: s => s.dsp_features?.bpm                   ?? null, ...LIBRARY_RANGE },
  { key: "spectral_centroid_mean",label: "Spec. Cent.", field: "dsp_features.spectral_centroid_mean", get: s => s.dsp_features?.spectral_centroid_mean ?? null, ...LIBRARY_RANGE },
];

// ── Other features (arrays excluded) ──────────────────────────────────────
export const OTHER_AXES: RadarAxis[] = [
  { key: "gmbi_valence",      label: "GMBI Val.",   field: "other_features.gmbi_valence",      get: s => s.other_features?.gmbi_valence      ?? null, ...Z_SCORE },
  { key: "gmbi_arousal",      label: "GMBI Arous.", field: "other_features.gmbi_arousal",      get: s => s.other_features?.gmbi_arousal      ?? null, ...Z_SCORE },
  { key: "gmbi_authenticity", label: "Authentic.",  field: "other_features.gmbi_authenticity", get: s => s.other_features?.gmbi_authenticity ?? null, ...Z_SCORE },
  { key: "gmbi_timeliness",   label: "Timely",      field: "other_features.gmbi_timeliness",   get: s => s.other_features?.gmbi_timeliness   ?? null, ...Z_SCORE },
  { key: "gmbi_complexity",   label: "Complexity",  field: "other_features.gmbi_complexity",   get: s => s.other_features?.gmbi_complexity   ?? null, ...Z_SCORE },
  { key: "tonal",             label: "Tonal",       field: "other_features.tonal",             get: s => s.other_features?.tonal             ?? null, ...PROBABILITY },
];

/** Compute per-axis min/max stats from the library for MinMax-normalised axes. */
export function computeAxisStats(songs: Song[], axes: RadarAxis[]): AxisStatsMap {
  const stats: AxisStatsMap = {};
  for (const ax of axes) {
    const vals = songs.map(ax.get).filter((v): v is number => v != null);
    stats[ax.key] =
      vals.length === 0
        ? { min: 0, max: 1 }
        : { min: Math.min(...vals), max: Math.max(...vals) };
  }
  return stats;
}
