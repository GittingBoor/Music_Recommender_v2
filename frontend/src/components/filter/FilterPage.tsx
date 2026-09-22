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

// ── colours ──────────────────────────────────────────────────────────────
const MOOD_COLORS: Record<string, string> = {
  happy:      "#fbbf24",
  sad:        "#60a5fa",
  aggressive: "#f87171",
  party:      "#e879f9",
  relaxed:    "#34d399",
  acoustic:   "#a78bfa",
  electronic: "#2dd4bf",
};

const DSP_COLORS: Record<string, string> = {
  danceability:          "#34d399",
  beat_confidence:       "#60a5fa",
  key_strength:          "#818cf8",
  dynamic_complexity:    "#fbbf24",
  onset_rate:            "#fb923c",
  dissonance:            "#f87171",
  bpm:                   "#f472b6",
  spectral_centroid_mean:"#2dd4bf",
};

const OTHER_COLORS: Record<string, string> = {
  gmbi_valence:      "#818cf8",
  gmbi_arousal:      "#fb923c",
  gmbi_authenticity: "#34d399",
  gmbi_timeliness:   "#60a5fa",
  gmbi_complexity:   "#f87171",
  tonal:             "#2dd4bf",
};

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
  colors: Record<string, string>,
): BarRow[] {
  return axes.map((ax) => {
    const histogram = new Array<number>(HIST_BINS).fill(0);
    for (const s of songs) {
      const raw = ax.get(s);
      if (raw == null) continue;
      const v = ax.norm(raw, stats[ax.key]);
      histogram[Math.min(HIST_BINS - 1, Math.floor(v * HIST_BINS))]++;
    }
    return { key: ax.key, label: ax.label, histogram, color: colors[ax.key] };
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

interface Props {
  songs: Song[];
}

export function FilterPage({ songs }: Props) {
  // ── text search ──────────────────────────────────────────────────────────
  const [search, setSearch] = useState("");

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
  const moodRows  = useMemo(() => axisRows(songs, MOOD_AXES,  moodStats,  MOOD_COLORS),  [songs, moodStats]);
  const dspRows   = useMemo(() => axisRows(songs, DSP_AXES,   dspStats,   DSP_COLORS),   [songs, dspStats]);
  const otherRows = useMemo(() => axisRows(songs, OTHER_AXES, otherStats, OTHER_COLORS), [songs, otherStats]);

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
    <div className="h-full flex">

      {/* ── left: all filters ── */}
      <aside className="w-72 xl:w-80 shrink-0 overflow-y-auto border-r border-gray-800 bg-gray-950">
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
          accentColor="#fbbf24"
        />
        <BarSliderFilter
          title="Instruments"
          rows={instrRows}
          thresholds={instrThresh}
          onChange={(k, v) => setOnePatch(setInstrThresh, k, v)}
          onReset={() => setInstrThresh({})}
          enabled={instrEnabled}
          onToggleEnabled={() => setInstrEnabled(e => !e)}
          accentColor="#2dd4bf"
        />
      </aside>

      {/* ── center: search + results (sortable; visible order = play queue) ── */}
      <section className="flex-1 min-w-0 overflow-y-auto">
        <div className="px-4 py-4 space-y-4">
          <div className="flex items-center gap-4 flex-wrap">
            <input
              type="text"
              placeholder="Search title or artist…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="flex-1 min-w-48 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-violet-500"
            />
            <span className="text-sm text-gray-500 shrink-0">
              <span className="text-white font-medium">{filtered.length}</span>
              {" "}/ {songs.length} songs
            </span>
            {hasActiveFilters && (
              <button
                onClick={resetAll}
                className="text-xs text-gray-500 hover:text-gray-200 border border-gray-700 hover:border-gray-500 px-3 py-2 rounded-lg transition-colors shrink-0"
              >
                Clear all filters
              </button>
            )}
          </div>

          <ResultsTable
            songs={filtered}
            onVisibleOrderChange={handleVisibleOrderChange}
          />
        </div>
      </section>

      {/* ── right: radar visualisation of thresholds vs. filtered average ── */}
      <aside className="hidden lg:flex w-64 xl:w-72 shrink-0 overflow-y-auto border-l border-gray-800 flex-col gap-3 p-3">
        <div className="flex items-center gap-3 text-[0.65rem] text-gray-500">
          <span className="flex items-center gap-1">
            <span className="w-3 h-2 rounded-sm bg-violet-400/40 border border-violet-400" /> Filter
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-2 rounded-sm border border-dashed border-gray-300/70" /> Ø filtered songs
          </span>
        </div>
        <RadarChart
          title="Moods"
          axes={MOOD_AXES}
          thresholds={moodThresh}
          profile={moodProfile}
          enabled={moodEnabled}
          axisColors={MOOD_COLORS}
        />
        <RadarChart
          title="DSP Features"
          axes={DSP_AXES}
          thresholds={dspThresh}
          profile={dspProfile}
          enabled={dspEnabled}
          axisColors={DSP_COLORS}
        />
        <RadarChart
          title="Other Features"
          axes={OTHER_AXES}
          thresholds={otherThresh}
          profile={otherProfile}
          enabled={otherEnabled}
          axisColors={OTHER_COLORS}
        />
      </aside>
    </div>
  );
}
