import type { Song } from "../../types/song";

export interface AxisStats {
  min: number;
  max: number;
}

export type AxisStatsMap = Record<string, AxisStats>;

export interface RadarAxis {
  key: string;
  label: string;
  get: (s: Song) => number | null;
  /** Returns a normalised 0–1 value for filtering. stats is provided but may be ignored. */
  norm: (v: number, stats: AxisStats) => number;
}

function clamp(v: number, lo = 0, hi = 1): number {
  return Math.max(lo, Math.min(hi, v));
}

function identity(v: number): number {
  return clamp(v);
}

function minMax(v: number, stats: AxisStats): number {
  if (stats.max === stats.min) return 0.5;
  return clamp((v - stats.min) / (stats.max - stats.min));
}

// ── Moods ──────────────────────────────────────────────────────────────────
export const MOOD_AXES: RadarAxis[] = [
  { key: "happy",      label: "Happy",      get: s => s.ml_moods?.happy      ?? null, norm: v => identity(v) },
  { key: "sad",        label: "Sad",        get: s => s.ml_moods?.sad        ?? null, norm: v => identity(v) },
  { key: "aggressive", label: "Aggressive", get: s => s.ml_moods?.aggressive ?? null, norm: v => identity(v) },
  { key: "party",      label: "Party",      get: s => s.ml_moods?.party      ?? null, norm: v => identity(v) },
  { key: "relaxed",    label: "Relaxed",    get: s => s.ml_moods?.relaxed    ?? null, norm: v => identity(v) },
  { key: "acoustic",   label: "Acoustic",   get: s => s.ml_moods?.acoustic   ?? null, norm: v => identity(v) },
  { key: "electronic", label: "Electronic", get: s => s.ml_moods?.electronic ?? null, norm: v => identity(v) },
];

// ── DSP features (curated subset, readable in a radar) ─────────────────────
export const DSP_AXES: RadarAxis[] = [
  { key: "danceability",          label: "Dance",       get: s => s.dsp_features?.danceability          ?? null, norm: v => identity(v) },
  { key: "beat_confidence",       label: "Beat Conf.",  get: s => s.dsp_features?.beat_confidence       ?? null, norm: v => identity(v) },
  { key: "key_strength",          label: "Key Str.",    get: s => s.dsp_features?.key_strength          ?? null, norm: v => identity(v) },
  { key: "dynamic_complexity",    label: "Dyn. Compl.", get: s => s.dsp_features?.dynamic_complexity    ?? null, norm: (v, stats) => minMax(v, stats) },
  { key: "onset_rate",            label: "Onset Rate",  get: s => s.dsp_features?.onset_rate            ?? null, norm: (v, stats) => minMax(v, stats) },
  { key: "dissonance",            label: "Dissonance",  get: s => s.dsp_features?.dissonance            ?? null, norm: (v, stats) => minMax(v, stats) },
  { key: "bpm",                   label: "BPM",         get: s => s.dsp_features?.bpm                   ?? null, norm: (v, stats) => minMax(v, stats) },
  { key: "spectral_centroid_mean",label: "Spec. Cent.", get: s => s.dsp_features?.spectral_centroid_mean ?? null, norm: (v, stats) => minMax(v, stats) },
];

// ── Other features (arrays excluded) ──────────────────────────────────────
export const OTHER_AXES: RadarAxis[] = [
  { key: "gmbi_valence",      label: "GMBI Val.",   get: s => s.other_features?.gmbi_valence      ?? null, norm: v => clamp((v + 2) / 4) },
  { key: "gmbi_arousal",      label: "GMBI Arous.", get: s => s.other_features?.gmbi_arousal      ?? null, norm: v => clamp((v + 2) / 4) },
  { key: "gmbi_authenticity", label: "Authentic.",  get: s => s.other_features?.gmbi_authenticity ?? null, norm: v => clamp((v + 2) / 4) },
  { key: "gmbi_timeliness",   label: "Timely",      get: s => s.other_features?.gmbi_timeliness   ?? null, norm: v => clamp((v + 2) / 4) },
  { key: "gmbi_complexity",   label: "Complexity",  get: s => s.other_features?.gmbi_complexity   ?? null, norm: v => clamp((v + 2) / 4) },
  { key: "tonal",             label: "Tonal",       get: s => s.other_features?.tonal             ?? null, norm: v => identity(v) },
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
