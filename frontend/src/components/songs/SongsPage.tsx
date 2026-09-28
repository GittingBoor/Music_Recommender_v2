import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Song } from "../../types/song";
import { setQueue } from "../../audio/player";
import {
  MOOD_AXES, DSP_AXES, OTHER_AXES,
  computeAxisStats,
} from "./featureConfig";
import type { RadarAxis, AxisStatsMap } from "./featureConfig";
import { RadarChart } from "./RadarChart";
import { BarSliderFilter } from "./BarSliderFilter";
import type { BarRow } from "./BarSliderFilter";
import { ResultsTable } from "./ResultsTable";

type ThresholdsMap = Record<string, number>;

function emptyThresholds(keys: string[]): ThresholdsMap {
  return Object.fromEntries(keys.map((k) => [k, 0]));
}

const HIST_BINS = 20;

/** Slider rows for radar axes, each with the library's distribution of normalised values. */
function axisRows(
  songs: Song[],
  axes: RadarAxis[],
  stats: AxisStatsMap,
): BarRow[] {
  return axes.map((ax) => {
    const histogram = new Array<number>(HIST_BINS).fill(0);
    for (const s of songs) {
      const raw = ax.get(s);
      if (raw == null) continue;
      const v = ax.norm(raw, stats[ax.key]);
      histogram[Math.min(HIST_BINS - 1, Math.floor(v * HIST_BINS))]++;
    }
    return { key: ax.key, label: ax.label, histogram };
  });
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
}

export function FilterPage({ songs }: Props) {
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

  // ── axis stats (library-wide min/max, computed once per songs change) ───
  const dspStats   = useMemo(() => computeAxisStats(songs, DSP_AXES),   [songs]);
  const otherStats = useMemo(() => computeAxisStats(songs, OTHER_AXES), [songs]);
  const moodStats  = useMemo(() => computeAxisStats(songs, MOOD_AXES),  [songs]);

  // ── slider rows for the radar axes ───────────────────────────────────────
  const moodRows  = useMemo(() => axisRows(songs, MOOD_AXES,  moodStats),  [songs, moodStats]);
  const dspRows   = useMemo(() => axisRows(songs, DSP_AXES,   dspStats),   [songs, dspStats]);
  const otherRows = useMemo(() => axisRows(songs, OTHER_AXES, otherStats), [songs, otherStats]);

  // ── genre rows ────────────────────────────────────────────────────────────
  const genreRows = useMemo<BarRow[]>(() => {
    const counts: Record<string, number> = {};
    for (const s of songs) {
      const top3 = [...s.parent_genres]
        .sort((a, b) => b.percentage - a.percentage)
        .slice(0, 3);
      for (const g of top3) {
        counts[g.genre] = (counts[g.genre] ?? 0) + 1;
      }
    }
    return Object.entries(counts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 25)
      .map(([genre, count]) => ({ key: genre, label: genre, count }));
  }, [songs]);

  // ── instrument rows ───────────────────────────────────────────────────────
  const instrRows = useMemo<BarRow[]>(() => {
    const counts: Record<string, number> = {};
    for (const s of songs) {
      const top10 = [...s.instruments]
        .sort((a, b) => b.probability - a.probability)
        .slice(0, 10);
      for (const inst of top10) {
        counts[inst.instrument] = (counts[inst.instrument] ?? 0) + 1;
      }
    }
    return Object.entries(counts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 25)
      .map(([name, count]) => ({ key: name, label: name, count }));
  }, [songs]);

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
  const handleVisibleOrderChange = useCallback((ids: string[]) => {
    setQueue(ids);
  }, []);

  // Restore the default queue (full library, DB order) when leaving the page.
  const allSongsRef = useRef(songs);
  allSongsRef.current = songs;
  useEffect(() => {
    return () => setQueue(allSongsRef.current.map((s) => s.id));
  }, []);

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

  function resetAll() {
    setSearch("");
    setMoodThresh(emptyThresholds(MOOD_AXES.map(a => a.key)));
    setDspThresh(emptyThresholds(DSP_AXES.map(a => a.key)));
    setOtherThresh(emptyThresholds(OTHER_AXES.map(a => a.key)));
    setGenreThresh({});
    setInstrThresh({});
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
      <aside className={`absolute inset-0 z-30 md:static md:z-auto w-full md:w-72 xl:w-80 shrink-0 overflow-y-auto border-r border-line bg-panel ${mobileFilters ? "block" : "hidden"} ${showPanels ? "md:block" : "md:hidden"}`}>
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
          title="Moods"
          rows={moodRows}
          thresholds={moodThresh}
          onChange={(k, v) => setOnePatch(setMoodThresh, k, v)}
          onReset={() => resetChart(setMoodThresh, MOOD_AXES.map(a => a.key))}
          enabled={moodEnabled}
          onToggleEnabled={() => setMoodEnabled(e => !e)}
        />
        <BarSliderFilter
          title="DSP Features"
          rows={dspRows}
          thresholds={dspThresh}
          onChange={(k, v) => setOnePatch(setDspThresh, k, v)}
          onReset={() => resetChart(setDspThresh, DSP_AXES.map(a => a.key))}
          enabled={dspEnabled}
          onToggleEnabled={() => setDspEnabled(e => !e)}
        />
        <BarSliderFilter
          title="Other Features"
          rows={otherRows}
          thresholds={otherThresh}
          onChange={(k, v) => setOnePatch(setOtherThresh, k, v)}
          onReset={() => resetChart(setOtherThresh, OTHER_AXES.map(a => a.key))}
          enabled={otherEnabled}
          onToggleEnabled={() => setOtherEnabled(e => !e)}
        />
        <BarSliderFilter
          title="Parent Genres"
          rows={genreRows}
          thresholds={genreThresh}
          onChange={(k, v) => setOnePatch(setGenreThresh, k, v)}
          onReset={() => setGenreThresh({})}
          enabled={genreEnabled}
          onToggleEnabled={() => setGenreEnabled(e => !e)}
        />
        <BarSliderFilter
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
      <section className="flex-1 min-w-0 overflow-y-auto">
        <div className="px-3 py-3 md:px-5 md:py-4 space-y-3 md:space-y-4">
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
              className="field flex-1 min-w-0 md:min-w-48"
            />
            <span className="font-mono text-2xs text-ink-3 shrink-0 tabular-nums">
              <span className="text-sm text-ink">{filtered.length}</span>
              {" "}/ {songs.length} songs
            </span>
            {hasActiveFilters && (
              <button
                onClick={resetAll}
                className="btn-quiet shrink-0"
              >
                Clear all filters
              </button>
            )}
          </div>

          <ResultsTable
            songs={filtered}
            onVisibleOrderChange={handleVisibleOrderChange}
            expandable
          />
        </div>
      </section>

      {/* ── right: radar visualisation of thresholds vs. filtered average ── */}
      <aside className={`w-64 xl:w-72 shrink-0 overflow-y-auto border-l border-line bg-panel flex-col gap-4 px-4 py-4 ${showPanels ? "hidden lg:flex" : "hidden"}`}>
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
