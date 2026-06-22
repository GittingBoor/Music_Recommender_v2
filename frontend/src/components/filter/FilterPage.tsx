import { useMemo, useState } from "react";
import type { Song } from "../../types/song";
import { PlayButton } from "../PlayButton";
import {
  MOOD_AXES, DSP_AXES, OTHER_AXES,
  computeAxisStats,
} from "./featureConfig";
import { RadarFilter } from "./RadarFilter";
import { BarSliderFilter } from "./BarSliderFilter";
import type { BarRow } from "./BarSliderFilter";

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

function fmtDuration(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
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

      // genre filter — percentage is 0-100, threshold is 0-1
      if (genreEnabled) {
        for (const [key, thresh] of Object.entries(genreThresh)) {
          if (thresh <= 0) continue;
          const match = song.parent_genres.find((g) => g.genre === key);
          if (!match || match.percentage / 100 < thresh) return false;
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
    <div className="h-full overflow-y-auto">
      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">

        {/* ── search bar + counter ── */}
        <div className="flex items-center gap-4 flex-wrap">
          <input
            type="text"
            placeholder="Search title or artist…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 min-w-60 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-violet-500"
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

        {/* ── filter charts ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          <RadarFilter
            title="Moods"
            axes={MOOD_AXES}
            stats={moodStats}
            thresholds={moodThresh}
            onChange={(k, v) => setOnePatch(setMoodThresh, k, v)}
            onReset={() => resetChart(setMoodThresh, MOOD_AXES.map(a => a.key))}
            enabled={moodEnabled}
            onToggleEnabled={() => setMoodEnabled(e => !e)}
            axisColors={MOOD_COLORS}
          />
          <RadarFilter
            title="DSP Features"
            axes={DSP_AXES}
            stats={dspStats}
            thresholds={dspThresh}
            onChange={(k, v) => setOnePatch(setDspThresh, k, v)}
            onReset={() => resetChart(setDspThresh, DSP_AXES.map(a => a.key))}
            enabled={dspEnabled}
            onToggleEnabled={() => setDspEnabled(e => !e)}
            axisColors={DSP_COLORS}
          />
          <RadarFilter
            title="Other Features"
            axes={OTHER_AXES}
            stats={otherStats}
            thresholds={otherThresh}
            onChange={(k, v) => setOnePatch(setOtherThresh, k, v)}
            onReset={() => resetChart(setOtherThresh, OTHER_AXES.map(a => a.key))}
            enabled={otherEnabled}
            onToggleEnabled={() => setOtherEnabled(e => !e)}
            axisColors={OTHER_COLORS}
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
        </div>

        {/* ── result list ── */}
        <div>
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
            Results
          </h2>
          {filtered.length === 0 ? (
            <div className="text-gray-600 text-sm text-center py-12 border border-dashed border-gray-800 rounded-lg">
              No songs match the current filters.
            </div>
          ) : (
            <div className="space-y-1">
              {filtered.map((song) => {
                const dsp  = song.dsp_features;
                const file = song.file_metadata;
                return (
                  <div
                    key={song.id}
                    className="flex items-center gap-3 px-3 py-2 rounded-lg bg-gray-900/40 border border-gray-800 hover:bg-gray-800/60 transition-colors"
                  >
                    <PlayButton songId={song.id} />
                    <div className="flex-1 min-w-0">
                      <span className="font-medium text-white text-sm truncate block">
                        {song.title ?? "Unknown"}
                      </span>
                      <span className="text-xs text-gray-400 truncate block">
                        {song.artist ?? "Unknown artist"}
                      </span>
                    </div>
                    <div className="hidden sm:flex items-center gap-1.5 shrink-0 flex-wrap justify-end max-w-xs">
                      {dsp?.key && dsp.scale && (
                        <span className="text-xs bg-gray-800 text-gray-300 px-2 py-0.5 rounded font-mono">
                          {dsp.key} {dsp.scale}
                        </span>
                      )}
                      {dsp?.bpm != null && (
                        <span className="text-xs bg-gray-800 text-gray-300 px-2 py-0.5 rounded font-mono">
                          {Math.round(dsp.bpm)} BPM
                        </span>
                      )}
                      {file?.duration_seconds != null && (
                        <span className="text-xs bg-gray-800 text-gray-300 px-2 py-0.5 rounded font-mono">
                          {fmtDuration(file.duration_seconds)}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
