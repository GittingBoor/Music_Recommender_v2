import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Song } from "../../types/song";
import { setQueue } from "../../audio/player";
import {
  MOOD_AXES, DSP_AXES, OTHER_AXES,
  computeAxisStats,
} from "../filter/featureConfig";
import type { RadarAxis, AxisStatsMap } from "../filter/featureConfig";
import { RadarChart } from "../filter/RadarChart";
import { BarSliderFilter } from "../filter/BarSliderFilter";
import type { BarRow } from "../filter/BarSliderFilter";
import { ResultsTable } from "./ResultsTable";
import { FIELD_DESCRIPTIONS } from "./fieldDescriptions";

type ThresholdsMap = Record<string, number>;

function emptyThresholds(keys: string[]): ThresholdsMap {
  return Object.fromEntries(keys.map((k) => [k, 0]));
}

const HIST_BINS = 20;

const HISTOGRAM_HINT = "Bars: how many songs lie at each slider position; orange = songs that pass.";

/** Bin counts of 0–1 values. */
function histogramOf(values: number[]): number[] {
  const histogram = new Array<number>(HIST_BINS).fill(0);
  for (const v of values) histogram[Math.min(HIST_BINS - 1, Math.floor(v * HIST_BINS))]++;
  return histogram;
}

/** Slider rows for radar axes, each with the library's distribution of normalised values. */
function axisRows(
  songs: Song[],
  axes: RadarAxis[],
  stats: AxisStatsMap,
): BarRow[] {
  return axes.map((ax) => {
    const values: number[] = [];
    for (const s of songs) {
      const raw = ax.get(s);
      if (raw != null) values.push(ax.norm(raw, stats[ax.key]));
    }
    const description = [FIELD_DESCRIPTIONS[ax.field], ax.scaleHint, HISTOGRAM_HINT].join("\n");
    return { key: ax.key, label: ax.label, histogram: histogramOf(values), description };
  });
}

/**
 * Slider rows for per-song lists (genres, instruments): the 25 entries most often
 * in a song's top N, each with the distribution of its value over the songs that have it.
 */
function listRows<T>(
  songs: Song[],
  itemsOf: (s: Song) => T[],
  name: (item: T) => string,
  value: (item: T) => number,
  topN: number,
  describe: (count: number) => string,
): BarRow[] {
  const counts: Record<string, number> = {};
  const values: Record<string, number[]> = {};
  for (const s of songs) {
    const items = [...itemsOf(s)].sort((a, b) => value(b) - value(a));
    items.forEach((item, rank) => {
      const key = name(item);
      (values[key] ??= []).push(value(item));
      if (rank < topN) counts[key] = (counts[key] ?? 0) + 1;
    });
  }
  return Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 25)
    .map(([key, count]) => ({
      key,
      label: key,
      count,
      histogram: histogramOf(values[key]),
      description: describe(count),
    }));
}

/** Mean normalised value per axis over the given songs (missing values skipped). */
function meanProfile(songs: Song[], axes: RadarAxis[], stats: AxisStatsMap): ThresholdsMap {
  const out: ThresholdsMap = {};
  for (const ax of axes) {
    let sum = 0;
    let n = 0;
    for (const s of songs) {
      const raw = ax.get(s);
      if (raw == null) continue;
      sum += ax.norm(raw, stats[ax.key]);
      n++;
    }
    if (n > 0) out[ax.key] = sum / n;
  }
  return out;
}

/** Boolean state that survives leaving the page (panel collapse). */
function usePersistentFlag(key: string, initial: boolean): [boolean, () => void] {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw == null ? initial : raw === "1";
    } catch {
      return initial;
    }
  });
  const toggle = useCallback(() => {
    setValue((v) => {
      try { localStorage.setItem(key, v ? "0" : "1"); } catch { /* storage unavailable */ }
      return !v;
    });
  }, [key]);
  return [value, toggle];
}

interface Props {
  songs: Song[];
  /** False while another page is shown (the page stays mounted to keep its state). */
  active: boolean;
}

/** Main page: the whole library as a sortable table, narrowed by the filters. */
export function SongsPage({ songs, active }: Props) {
  // ── text search ──────────────────────────────────────────────────────────
  const [search, setSearch] = useState("");

  // ── side panels (collapse both for a full-width results table) ───────────
  const [showPanels, togglePanels] = usePersistentFlag("filter.showPanels", true);
  // Phones get the filters as a full-screen overlay, closed by default.
  const [mobileFilters, setMobileFilters] = useState(false);

  // ── per-chart state ──────────────────────────────────────────────────────
  const [moodThresh, setMoodThresh]     = useState<ThresholdsMap>(() => emptyThresholds(MOOD_AXES.map(a => a.key)));
  const [moodEnabled, setMoodEnabled]   = useState(true);

  const [dspThresh, setDspThresh]       = useState<ThresholdsMap>(() => emptyThresholds(DSP_AXES.map(a => a.key)));
  const [dspEnabled, setDspEnabled]     = useState(true);

  const [otherThresh, setOtherThresh]   = useState<ThresholdsMap>(() => emptyThresholds(OTHER_AXES.map(a => a.key)));
  const [otherEnabled, setOtherEnabled] = useState(true);

  const [genreThresh, setGenreThresh]   = useState<ThresholdsMap>({});
  const [genreEnabled, setGenreEnabled] = useState(true);

  const [instrThresh, setInstrThresh]   = useState<ThresholdsMap>({});
  const [instrEnabled, setInstrEnabled] = useState(true);

  // Bumped by "Reset all": remounts the table (sort order) and the filter panels (collapse state).
  const [resetKey, setResetKey] = useState(0);
  const filterPanelRef = useRef<HTMLElement>(null);
  const resultsRef = useRef<HTMLElement>(null);
  const radarPanelRef = useRef<HTMLElement>(null);

  // ── axis stats (library-wide min/max, computed once per songs change) ───
  const dspStats   = useMemo(() => computeAxisStats(songs, DSP_AXES),   [songs]);
  const otherStats = useMemo(() => computeAxisStats(songs, OTHER_AXES), [songs]);
  const moodStats  = useMemo(() => computeAxisStats(songs, MOOD_AXES),  [songs]);

  // ── slider rows for the radar axes ───────────────────────────────────────
  const moodRows  = useMemo(() => axisRows(songs, MOOD_AXES,  moodStats),  [songs, moodStats]);
  const dspRows   = useMemo(() => axisRows(songs, DSP_AXES,   dspStats),   [songs, dspStats]);
  const otherRows = useMemo(() => axisRows(songs, OTHER_AXES, otherStats), [songs, otherStats]);

  // ── genre rows ────────────────────────────────────────────────────────────
  // percentage is a 0-1 share (despite the name)
  const genreRows = useMemo(() => listRows(
    songs, (s) => s.parent_genres, (g) => g.genre, (g) => g.percentage, 3,
    (count) => [
      "Share of this genre in the song; all parent genres of a song add up to 100%.",
      "Slider = minimum share (30% = at least 30% of the song is this genre).",
      `Number: ${count} songs have it among their top 3 genres.`,
      "Bars: how the share spreads over the songs that have this genre; orange = songs that pass.",
    ].join("\n"),
  ), [songs]);

  // ── instrument rows ───────────────────────────────────────────────────────
  const instrRows = useMemo(() => listRows(
    songs, (s) => s.instruments, (i) => i.instrument, (i) => i.probability, 10,
    (count) => [
      "Model probability that the instrument is present; independent per instrument, they don't add up to 100%.",
      "Slider = minimum probability (50% = 0.50).",
      `Number: ${count} songs have it among their top 10 instruments.`,
      "Bars: how the probability spreads over the songs that have this instrument; orange = songs that pass.",
    ].join("\n"),
  ), [songs]);

  // ── filtered result ───────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    const q = search.toLowerCase();

    return songs.filter((song) => {
      // text search
      if (q && !song.title?.toLowerCase().includes(q) && !song.artist?.toLowerCase().includes(q)) {
        return false;
      }

      // mood radar
      if (moodEnabled) {
        for (const ax of MOOD_AXES) {
          const thresh = moodThresh[ax.key] ?? 0;
          if (thresh <= 0) continue;
          const raw = ax.get(song);
          if (raw == null) return false;
          if (ax.norm(raw, moodStats[ax.key]) < thresh) return false;
        }
      }

      // dsp radar
      if (dspEnabled) {
        for (const ax of DSP_AXES) {
          const thresh = dspThresh[ax.key] ?? 0;
          if (thresh <= 0) continue;
          const raw = ax.get(song);
          if (raw == null) return false;
          if (ax.norm(raw, dspStats[ax.key]) < thresh) return false;
        }
      }

      // other radar
      if (otherEnabled) {
        for (const ax of OTHER_AXES) {
          const thresh = otherThresh[ax.key] ?? 0;
          if (thresh <= 0) continue;
          const raw = ax.get(song);
          if (raw == null) return false;
          if (ax.norm(raw, otherStats[ax.key]) < thresh) return false;
        }
      }

      // genre filter — percentage is a 0-1 share (despite the name)
      if (genreEnabled) {
        for (const [key, thresh] of Object.entries(genreThresh)) {
          if (thresh <= 0) continue;
          const match = song.parent_genres.find((g) => g.genre === key);
          if (!match || match.percentage < thresh) return false;
        }
      }

      // instrument filter — probability is 0-1
      if (instrEnabled) {
        for (const [key, thresh] of Object.entries(instrThresh)) {
          if (thresh <= 0) continue;
          const match = song.instruments.find((i) => i.instrument === key);
          if (!match || match.probability < thresh) return false;
        }
      }

      return true;
    });
  }, [
    songs, search,
    moodEnabled, moodThresh, moodStats,
    dspEnabled, dspThresh, dspStats,
    otherEnabled, otherThresh, otherStats,
    genreEnabled, genreThresh,
    instrEnabled, instrThresh,
  ]);

  // ── average profile of the filtered songs (radar visualisation) ─────────
  const moodProfile  = useMemo(() => meanProfile(filtered, MOOD_AXES,  moodStats),  [filtered, moodStats]);
  const dspProfile   = useMemo(() => meanProfile(filtered, DSP_AXES,   dspStats),   [filtered, dspStats]);
  const otherProfile = useMemo(() => meanProfile(filtered, OTHER_AXES, otherStats), [filtered, otherStats]);

  // ── play queue follows the visible table order while this page is open ────
  // ("open" includes a song detail page on top of the list.)
  const visibleOrderRef = useRef<string[]>([]);
  const activeRef = useRef(active);
  activeRef.current = active;
  const handleVisibleOrderChange = useCallback((ids: string[]) => {
    visibleOrderRef.current = ids;
    if (activeRef.current) setQueue(ids);
  }, []);

  // Leaving the page restores the default queue (full library, DB order);
  // coming back puts the table order back in place.
  const allSongsRef = useRef(songs);
  allSongsRef.current = songs;
  useEffect(() => {
    setQueue(active ? visibleOrderRef.current : allSongsRef.current.map((s) => s.id));
  }, [active]);

  // ── helpers ───────────────────────────────────────────────────────────────
  function setOnePatch(
    setter: React.Dispatch<React.SetStateAction<ThresholdsMap>>,
    key: string,
    val: number,
  ) {
    setter((prev) => ({ ...prev, [key]: val }));
  }

  function resetChart(
    setter: React.Dispatch<React.SetStateAction<ThresholdsMap>>,
    keys: string[],
  ) {
    setter(emptyThresholds(keys));
  }

  function clearFilters() {
    setSearch("");
    setMoodThresh(emptyThresholds(MOOD_AXES.map(a => a.key)));
    setDspThresh(emptyThresholds(DSP_AXES.map(a => a.key)));
    setOtherThresh(emptyThresholds(OTHER_AXES.map(a => a.key)));
    setGenreThresh({});
    setInstrThresh({});
  }

  /** Back to the page's initial state: no filters, all charts on, default sort, scrolled to the top. */
  function resetAll() {
    clearFilters();
    setMoodEnabled(true);
    setDspEnabled(true);
    setOtherEnabled(true);
    setGenreEnabled(true);
    setInstrEnabled(true);
    setResetKey((k) => k + 1);
    for (const el of [filterPanelRef.current, resultsRef.current, radarPanelRef.current]) {
      el?.scrollTo({ top: 0 });
    }
  }

  const hasActiveFilters =
    search !== "" ||
    Object.values(moodThresh).some(v => v > 0) ||
    Object.values(dspThresh).some(v => v > 0) ||
    Object.values(otherThresh).some(v => v > 0) ||
    Object.values(genreThresh).some(v => v > 0) ||
    Object.values(instrThresh).some(v => v > 0);

  return (
    <div className="h-full flex relative">

      {/* ── left: all filters (full-screen overlay on phones) ── */}
      <aside ref={filterPanelRef} className={`absolute inset-0 z-30 md:static md:z-auto w-full md:w-72 shrink-0 overflow-y-auto border-r border-line bg-panel ${mobileFilters ? "block" : "hidden"} ${showPanels ? "md:block" : "md:hidden"}`}>
        <div className="md:hidden sticky top-0 z-10 flex items-center justify-between px-4 py-2 bg-panel border-b border-line">
          <span className="font-mono text-2xs text-ink-3 tabular-nums">
            <span className="text-sm text-ink">{filtered.length}</span> / {songs.length} songs
          </span>
          <button
            onClick={() => setMobileFilters(false)}
            className="btn btn-primary h-8"
          >
            Show results
          </button>
        </div>
        <BarSliderFilter
          key={`Moods-${resetKey}`}
          title="Moods"
          rows={moodRows}
          thresholds={moodThresh}
          onChange={(k, v) => setOnePatch(setMoodThresh, k, v)}
          onReset={() => resetChart(setMoodThresh, MOOD_AXES.map(a => a.key))}
          enabled={moodEnabled}
          onToggleEnabled={() => setMoodEnabled(e => !e)}
        />
        <BarSliderFilter
          key={`DSP Features-${resetKey}`}
          title="DSP Features"
          rows={dspRows}
          thresholds={dspThresh}
          onChange={(k, v) => setOnePatch(setDspThresh, k, v)}
          onReset={() => resetChart(setDspThresh, DSP_AXES.map(a => a.key))}
          enabled={dspEnabled}
          onToggleEnabled={() => setDspEnabled(e => !e)}
        />
        <BarSliderFilter
          key={`Other Features-${resetKey}`}
          title="Other Features"
          rows={otherRows}
          thresholds={otherThresh}
          onChange={(k, v) => setOnePatch(setOtherThresh, k, v)}
          onReset={() => resetChart(setOtherThresh, OTHER_AXES.map(a => a.key))}
          enabled={otherEnabled}
          onToggleEnabled={() => setOtherEnabled(e => !e)}
        />
        <BarSliderFilter
          key={`Parent Genres-${resetKey}`}
          title="Parent Genres"
          rows={genreRows}
          thresholds={genreThresh}
          onChange={(k, v) => setOnePatch(setGenreThresh, k, v)}
          onReset={() => setGenreThresh({})}
          enabled={genreEnabled}
          onToggleEnabled={() => setGenreEnabled(e => !e)}
        />
        <BarSliderFilter
          key={`Instruments-${resetKey}`}
          title="Instruments"
          rows={instrRows}
          thresholds={instrThresh}
          onChange={(k, v) => setOnePatch(setInstrThresh, k, v)}
          onReset={() => setInstrThresh({})}
          enabled={instrEnabled}
          onToggleEnabled={() => setInstrEnabled(e => !e)}
        />
      </aside>

      {/* ── center: search + results (sortable; visible order = play queue) ── */}
      <section ref={resultsRef} className="flex-1 min-w-0 overflow-y-auto">
        <div className="px-3 py-3 md:px-4 md:py-4 space-y-3 md:space-y-4">
          <div className="flex items-center gap-2 md:gap-3 flex-wrap">
            <button
              onClick={() => (window.matchMedia("(min-width: 768px)").matches ? togglePanels() : setMobileFilters(true))}
              className={`btn h-8 ${showPanels ? "" : "border-signal text-signal"}`}
              aria-pressed={!showPanels}
              title={showPanels ? "Hide filters and charts" : "Show filters and charts"}
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>
              Filters
            </button>
            <input
              type="text"
              placeholder="Search title or artist…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="field flex-1 min-w-32 md:min-w-48"
            />
            <span className="font-mono text-2xs text-ink-3 shrink-0 tabular-nums">
              <span className="text-sm text-ink">{filtered.length}</span>
              {" "}/ {songs.length} songs
            </span>
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="btn-quiet shrink-0"
              >
                Clear all filters
              </button>
            )}
            <button
              onClick={resetAll}
              className="btn h-8 shrink-0"
              title="Clear every filter, turn all charts back on, restore the default sort and scroll to the top"
            >
              Reset all
            </button>
          </div>

          <ResultsTable
            key={resetKey}
            songs={filtered}
            onVisibleOrderChange={handleVisibleOrderChange}
          />
        </div>
      </section>

      {/* ── right: radar visualisation of thresholds vs. filtered average ── */}
      <aside ref={radarPanelRef} className={`w-64 shrink-0 overflow-y-auto border-l border-line bg-panel flex-col gap-4 px-4 py-4 ${showPanels ? "hidden lg:flex" : "hidden"}`}>
        <div className="flex items-center gap-4 font-mono text-2xs text-ink-3 pb-3 border-b border-line">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-2 bg-signal/25 border border-signal" /> Filter
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-2 border border-dashed border-ink/70" /> Ø filtered songs
          </span>
        </div>
        <RadarChart
          title="Moods"
          axes={MOOD_AXES}
          thresholds={moodThresh}
          profile={moodProfile}
          enabled={moodEnabled}
        />
        <RadarChart
          title="DSP Features"
          axes={DSP_AXES}
          thresholds={dspThresh}
          profile={dspProfile}
          enabled={dspEnabled}
        />
        <RadarChart
          title="Other Features"
          axes={OTHER_AXES}
          thresholds={otherThresh}
          profile={otherProfile}
          enabled={otherEnabled}
        />
      </aside>
    </div>
  );
}
