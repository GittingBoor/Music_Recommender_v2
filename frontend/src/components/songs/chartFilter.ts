import type { Song } from "../../types/song";

// Filters a click on an Analysis chart puts on the Songs page, as URL query
// (/songs?year=2020). The song values below are the ones the charts count, so
// a bar and the list it opens show the same songs.

export const PARENT_GENRES_PER_SONG = 3;
export const DETAILED_GENRES_PER_SONG = 5;
export const INSTRUMENTS_PER_SONG = 10;
const FIRST_YEAR = 1900;
const LAST_YEAR = 2030;

export type RangeField = "bpm" | "duration" | "danceability";
type ValueField = "key" | "scale" | "mood" | "artist" | "genre" | "detailed_genre" | "instrument";

export type ChartFilter =
  | { readonly field: "year"; readonly year: number }
  /** min inclusive, max exclusive; max null = open end (a histogram's last bin). */
  | { readonly field: RangeField; readonly min: number; readonly max: number | null }
  | { readonly field: ValueField; readonly value: string };

const RANGE_FIELDS: readonly RangeField[] = ["bpm", "duration", "danceability"];
const VALUE_FIELDS: readonly ValueField[] = ["key", "scale", "mood", "artist", "genre", "detailed_genre", "instrument"];

const LABELS: Record<ChartFilter["field"], string> = {
  year: "Release year",
  bpm: "BPM",
  duration: "Duration",
  danceability: "Danceability",
  key: "Key",
  scale: "Scale",
  mood: "Dominant mood",
  artist: "Artist",
  genre: "Parent genre",
  detailed_genre: "Detailed genre",
  instrument: "Instrument",
};

// ── song values as the Analysis charts count them ─────────────────────────────

export function releaseYear(song: Song): number | null {
  const date = song.track_metadata?.release_date;
  if (!date) return null;
  const year = parseInt(date.slice(0, 4), 10);
  return !isNaN(year) && year > FIRST_YEAR && year <= LAST_YEAR ? year : null;
}

export function rangeValue(song: Song, field: RangeField): number | null {
  switch (field) {
    case "bpm": return song.dsp_features?.bpm ?? null;
    case "duration": return song.file_metadata?.duration_seconds ?? null;
    case "danceability": return song.dsp_features?.danceability ?? null;
  }
}

export function dominantMood(song: Song): string | null {
  if (!song.ml_moods) return null;
  const entries = Object.entries(song.ml_moods).filter((e): e is [string, number] => e[1] != null);
  if (!entries.length) return null;
  return entries.sort(([, a], [, b]) => b - a)[0][0];
}

export function artistName(song: Song): string {
  return song.artist ?? "Unknown";
}

export function topParentGenres(song: Song): string[] {
  return [...song.parent_genres]
    .sort((a, b) => b.percentage - a.percentage)
    .slice(0, PARENT_GENRES_PER_SONG)
    .map((g) => g.genre);
}

export function topDetailedGenres(song: Song): string[] {
  return [...song.detailed_genres]
    .sort((a, b) => b.probability - a.probability)
    .slice(0, DETAILED_GENRES_PER_SONG)
    .map((g) => g.genre.split("---").pop() ?? g.genre);
}

export function topInstruments(song: Song): string[] {
  return [...song.instruments]
    .sort((a, b) => b.probability - a.probability)
    .slice(0, INSTRUMENTS_PER_SONG)
    .map((i) => i.instrument);
}

// ── matching ─────────────────────────────────────────────────────────────────

export function matchesChartFilter(song: Song, filter: ChartFilter): boolean {
  switch (filter.field) {
    case "year": return releaseYear(song) === filter.year;
    case "bpm":
    case "duration":
    case "danceability": {
      const v = rangeValue(song, filter.field);
      return v != null && v >= filter.min && (filter.max == null || v < filter.max);
    }
    case "key": return song.dsp_features?.key === filter.value;
    case "scale": return song.dsp_features?.scale === filter.value;
    case "mood": return dominantMood(song) === filter.value;
    case "artist": return artistName(song) === filter.value;
    case "genre": return topParentGenres(song).includes(filter.value);
    case "detailed_genre": return topDetailedGenres(song).includes(filter.value);
    case "instrument": return topInstruments(song).includes(filter.value);
  }
}

// ── URL ──────────────────────────────────────────────────────────────────────

// Bin edges are sums of floats (103.30999999999999); a few digits less keep the URL readable.
const URL_PRECISION = 12;

function tidy(edge: number): string {
  return String(Number(edge.toPrecision(URL_PRECISION)));
}

function paramValue(filter: ChartFilter): string {
  switch (filter.field) {
    case "year": return String(filter.year);
    case "bpm":
    case "duration":
    case "danceability": return `${tidy(filter.min)}_${filter.max == null ? "" : tidy(filter.max)}`;
    default: return filter.value;
  }
}

export function chartFilterQuery(filters: readonly ChartFilter[]): string {
  const params = new URLSearchParams(filters.map((f) => [f.field, paramValue(f)]));
  const query = params.toString();
  return query ? `?${query}` : "";
}

/** The Songs page showing only the songs of one chart value. */
export function songsPathFor(filter: ChartFilter): string {
  return `/songs${chartFilterQuery([filter])}`;
}

function parseRange(field: RangeField, raw: string): ChartFilter | null {
  const [lo, hi = ""] = raw.split("_");
  const min = Number(lo);
  const max = hi === "" ? null : Number(hi);
  if (lo === "" || isNaN(min) || (max != null && isNaN(max))) return null;
  return { field, min, max };
}

/** Chart filters of a query string; unknown or malformed parameters are ignored. */
export function parseChartFilters(search: string): ChartFilter[] {
  const filters: ChartFilter[] = [];
  for (const [name, raw] of new URLSearchParams(search)) {
    if (name === "year") {
      const year = Number(raw);
      if (Number.isInteger(year)) filters.push({ field: "year", year });
    } else if ((RANGE_FIELDS as readonly string[]).includes(name)) {
      const range = parseRange(name as RangeField, raw);
      if (range) filters.push(range);
    } else if ((VALUE_FIELDS as readonly string[]).includes(name) && raw !== "") {
      filters.push({ field: name as ValueField, value: raw });
    }
  }
  return filters;
}

// ── labels ───────────────────────────────────────────────────────────────────

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatRangeValue(field: RangeField, v: number): string {
  switch (field) {
    case "bpm": return v.toFixed(0);
    case "duration": return formatDuration(v);
    case "danceability": return v.toFixed(2);
  }
}

export function describeChartFilter(filter: ChartFilter): string {
  const label = LABELS[filter.field];
  switch (filter.field) {
    case "year": return `${label}: ${filter.year}`;
    case "bpm":
    case "duration":
    case "danceability": {
      const lo = formatRangeValue(filter.field, filter.min);
      return filter.max == null
        ? `${label}: ≥ ${lo}`
        : `${label}: ${lo} – ${formatRangeValue(filter.field, filter.max)}`;
    }
    default: return `${label}: ${filter.value}`;
  }
}
