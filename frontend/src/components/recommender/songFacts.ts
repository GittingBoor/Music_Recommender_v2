import type { MLMoods, Song } from "../../types/song";

/** A named score, e.g. a genre share or a mood probability (0–1). */
export interface Scored {
  readonly name: string;
  readonly value: number;
}

const MOOD_KEYS: readonly (keyof MLMoods)[] = [
  "happy", "sad", "aggressive", "party", "relaxed", "acoustic", "electronic",
];

export function bpmOf(song: Song): number | null {
  const bpm = song.dsp_features?.bpm;
  return bpm == null ? null : Math.round(bpm);
}

export function keyOf(song: Song): string | null {
  const dsp = song.dsp_features;
  return dsp?.key ? `${dsp.key} ${dsp.scale ?? ""}`.trim() : null;
}

/** Parent genre with the largest share (percentage is a 0–1 share despite the name). */
export function topGenre(song: Song): Scored | null {
  let best: Scored | null = null;
  for (const g of song.parent_genres) {
    if (!best || g.percentage > best.value) best = { name: g.genre, value: g.percentage };
  }
  return best;
}

/** Moods sorted by probability, highest first; missing values are skipped. */
export function rankedMoods(song: Song): Scored[] {
  const moods = song.ml_moods;
  if (!moods) return [];
  const out: Scored[] = [];
  for (const key of MOOD_KEYS) {
    const v = moods[key];
    if (v != null) out.push({ name: key, value: v });
  }
  return out.sort((a, b) => b.value - a.value);
}

export const pct = (v: number): string => `${Math.round(v * 100)}%`;

export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
