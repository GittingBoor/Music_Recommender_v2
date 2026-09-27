import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ComposedChart, AreaChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from "recharts";
import type { TooltipProps } from "recharts";
import { fetchTimeseries } from "../../services/api";
import type { Song } from "../../types/song";
import type { TimeAxisMode, TimeseriesResponse } from "../../types/analysis";

const FEATURES: { key: string; label: string; group: string; tooltip: string }[] = [
  { key: "loudness",           label: "Loudness",           group: "DSP",        tooltip: "Short-term loudness changes over the song (in dB)." },
  { key: "spectral_centroid",  label: "Spectral Centroid",  group: "DSP",        tooltip: "Average frequency of the sound — brighter/thinner sounds = higher values." },
  { key: "spectral_rolloff",   label: "Spectral Rolloff",   group: "DSP",        tooltip: "Frequency below which 85% of signal energy falls — measure of brightness." },
  { key: "spectral_flux",      label: "Spectral Flux",      group: "DSP",        tooltip: "Rate of spectral change — how quickly the sound character shifts over time." },
  { key: "zero_crossing_rate", label: "Zero Crossing Rate", group: "DSP",        tooltip: "How often the signal crosses zero — relates to noisiness and percussiveness." },
  { key: "dissonance",         label: "Dissonance",         group: "DSP",        tooltip: "Harmonic roughness — higher values = more tense or dissonant sound." },
  { key: "arousal",            label: "Arousal",            group: "ML Profile", tooltip: "Energy / intensity level of the song (ML model)." },
  { key: "valence",            label: "Valence",            group: "ML Profile", tooltip: "Positivity / happiness of the song's mood (ML model)." },
  { key: "approachability",    label: "Approachability",    group: "ML Profile", tooltip: "How niche or accessible the song sounds to a general audience." },
  { key: "engagement",         label: "Engagement",         group: "ML Profile", tooltip: "Active vs. background listening — high = foreground / active listening." },
  { key: "voice",              label: "Voice",              group: "ML Profile", tooltip: "Vocal presence — high = strong vocal, low = mostly instrumental." },
  { key: "gender",             label: "Gender",             group: "ML Profile", tooltip: "Perceived vocalist gender — high = female, low = male." },
  { key: "happy",              label: "Happy",              group: "Mood",       tooltip: "Probability the song conveys a happy mood." },
  { key: "sad",                label: "Sad",                group: "Mood",       tooltip: "Probability the song conveys a sad mood." },
  { key: "aggressive",         label: "Aggressive",         group: "Mood",       tooltip: "Probability the song conveys aggression or high intensity." },
  { key: "party",              label: "Party",              group: "Mood",       tooltip: "Probability the song fits a party / dance context." },
  { key: "relaxed",            label: "Relaxed",            group: "Mood",       tooltip: "Probability the song conveys a relaxed or calm mood." },
  { key: "acoustic",           label: "Acoustic",           group: "Mood",       tooltip: "Likelihood of acoustic instrumentation (vs electronic)." },
  { key: "electronic",         label: "Electronic",         group: "Mood",       tooltip: "Likelihood of electronic instrumentation (vs acoustic)." },
];

const MOODS = ["happy", "sad", "aggressive", "party", "relaxed", "acoustic", "electronic"];

const QUICK_GROUPS = [
  { group: "Mood",       labelCls: "text-violet-500/60",  activeCls: "bg-violet-600 text-white"  },
  { group: "ML Profile", labelCls: "text-blue-500/60",    activeCls: "bg-blue-600 text-white"    },
  { group: "DSP",        labelCls: "text-emerald-500/60", activeCls: "bg-emerald-600 text-white" },
] as const;

const TOOLTIP_STYLE: React.CSSProperties = {
  backgroundColor: "#111827",
  border: "1px solid #374151",
  borderRadius: 6,
  color: "#f3f4f6",
  fontSize: 12,
};

const AXIS_STYLE = { fill: "#6b7280", fontSize: 11 };
const GRID_STYLE = { stroke: "#1f2937" };
const YAXIS_WIDTH = 40;
const COUNT_CHART_HEIGHT = 70;
const VALUE_DECIMALS = 3;
const RELATIVE_AXIS_MAX = 100;
const RELATIVE_TICK_STEP = 10;
const ABSOLUTE_TICK_STEP = 20;
const ABSOLUTE_AXIS_ROUNDING = 60;
const ABSOLUTE_STEP_SECONDS = 1;

const MODE_OPTIONS: { readonly mode: TimeAxisMode; readonly label: string }[] = [
  { mode: "relative", label: "Relative time (%)" },
  { mode: "absolute", label: "Absolute time (s)" },
];

const formatTime = (sec: number): string => {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
};

const formatPercent = (pct: number): string => `${Math.round(pct)}%`;

const roundValue = (value: number | null | undefined): number | undefined =>
  value != null ? parseFloat(value.toFixed(VALUE_DECIMALS)) : undefined;

interface ChartEntry {
  x: number;
  avg?: number;
  band?: [number, number];
  song?: number;
  count: number;
}


interface Props {
  songs: Song[];
}

export function TimeseriesSection({ songs }: Props) {
  const [feature,   setFeature]   = useState("loudness");
  const [mood,      setMood]      = useState<string>("");
  const [threshold, setThreshold] = useState(0.7);
  const [songId,    setSongId]    = useState<string>("");
  const [search,    setSearch]    = useState("");
  const [showDrop,  setShowDrop]  = useState(false);
  const [mode,      setMode]      = useState<TimeAxisMode>("relative");

  const [tsData,  setTsData]  = useState<TimeseriesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  const dropRef = useRef<HTMLDivElement>(null);

  const filteredSongs = useMemo(() => {
    const q = search.toLowerCase();
    return songs
      .filter(
        (s) =>
          (s.title?.toLowerCase().includes(q) || s.artist?.toLowerCase().includes(q)) &&
          s.id !== songId,
      )
      .slice(0, 30);
  }, [songs, search, songId]);

  const selectedSong = useMemo(
    () => songs.find((s) => s.id === songId) ?? null,
    [songs, songId],
  );

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchTimeseries(feature, mood || null, threshold, songId || null, mode)
      .then(setTsData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [feature, mood, threshold, songId, mode]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) {
        setShowDrop(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const isRelative = (tsData?.mode ?? mode) === "relative";

  const chartData = useMemo<ChartEntry[]>(() => {
    if (!tsData) return [];
    const songValues = tsData.selected_song?.values ?? [];
    const len        = Math.max(tsData.positions.length, songValues.length);
    return Array.from({ length: len }, (_, i) => {
      const p25 = roundValue(tsData.p25_timeseries[i]);
      const p75 = roundValue(tsData.p75_timeseries[i]);
      return {
        x:     tsData.positions[i] ?? i * ABSOLUTE_STEP_SECONDS,
        avg:   roundValue(tsData.avg_timeseries[i]),
        band:  p25 != null && p75 != null ? [p25, p75] : undefined,
        song:  roundValue(songValues[i]),
        count: tsData.counts_at_time[i] ?? 0,
      };
    });
  }, [tsData]);

  const xAxisMax = useMemo(() => {
    if (isRelative) return RELATIVE_AXIS_MAX;
    const lastSec = chartData[chartData.length - 1]?.x ?? 0;
    if (lastSec === 0) return ABSOLUTE_AXIS_ROUNDING;
    return Math.ceil(lastSec / ABSOLUTE_AXIS_ROUNDING) * ABSOLUTE_AXIS_ROUNDING;
  }, [chartData, isRelative]);

  const xAxisTicks = useMemo(() => {
    const step = isRelative ? RELATIVE_TICK_STEP : ABSOLUTE_TICK_STEP;
    const ticks: number[] = [];
    for (let t = 0; t <= xAxisMax; t += step) ticks.push(t);
    return ticks;
  }, [xAxisMax, isRelative]);

  const formatX = isRelative ? formatPercent : formatTime;

  const featureLabel = FEATURES.find((f) => f.key === feature)?.label ?? feature;

  const renderTooltip = useCallback(
    ({ active, payload, label }: TooltipProps<number, string>): React.ReactNode => {
      if (!active || !payload?.length) return null;
      const chartEntry = payload[0]?.payload as ChartEntry | undefined;
      const count      = chartEntry?.count ?? 0;
      const totalCount = tsData?.song_count ?? 0;
      return (
        <div style={TOOLTIP_STYLE} className="px-3 py-2 space-y-1">
          <p className="text-gray-300 font-medium">{formatX((label as number) ?? 0)}</p>
          {payload.map((entry, i) => {
            const value = entry.value as number | [number, number];
            return (
              <p key={i} style={{ color: entry.color }}>
                {entry.name}:{" "}
                <span className="font-mono">
                  {Array.isArray(value)
                    ? `${value[0].toFixed(VALUE_DECIMALS)} – ${value[1].toFixed(VALUE_DECIMALS)}`
                    : value.toFixed(VALUE_DECIMALS)}
                </span>
              </p>
            );
          })}
          <p className="text-gray-500 text-[11px] pt-1 border-t border-gray-700/60">
            {count} / {totalCount} songs active at this point
          </p>
        </div>
      );
    },
    [tsData, formatX],
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-4 md:px-6 md:py-6 space-y-5">
      <div>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest">
          Timeseries Analysis
        </h2>
        <p className="text-xs text-gray-600 mt-1">
          Compare individual songs against the normalized average of a filtered group.
          Y-axis is min-max normalized (0–1) per song/group.
        </p>
      </div>

      {/* Controls — 3 visually distinct sections */}
      <div className="flex flex-col md:flex-row rounded-lg border border-gray-700 text-sm">
        {/* Section 1: Feature */}
        <div className="flex-1 min-w-0 px-4 py-3 bg-gray-900 rounded-t-lg md:rounded-tr-none md:rounded-l-lg">
          <label className="block text-xs text-gray-500 mb-1.5 uppercase tracking-wider">
            Feature
          </label>
          <select
            value={feature}
            onChange={(e) => setFeature(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-violet-500"
          >
            {["DSP", "ML Profile", "Mood"].map((group) => (
              <optgroup key={group} label={group}>
                {FEATURES.filter((f) => f.group === group).map((f) => (
                  <option key={f.key} value={f.key}>{f.label}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>

        {/* Divider */}
        <div className="h-px md:h-auto md:w-px bg-gray-700 shrink-0" />

        {/* Section 2: Group avg filter */}
        <div className="flex-[2] min-w-0 px-4 py-3 bg-gray-900/40">
          <label className="block text-xs text-gray-500 mb-1.5 uppercase tracking-wider">
            Group avg filter
          </label>
          <div className="flex gap-3 items-end">
            <div className="flex-1 min-w-0">
              <p className="text-[11px] text-gray-600 mb-1">Mood</p>
              <select
                value={mood}
                onChange={(e) => setMood(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-violet-500"
              >
                <option value="">All songs</option>
                {MOODS.map((m) => (
                  <option key={m} value={m}>{m.charAt(0).toUpperCase() + m.slice(1)}</option>
                ))}
              </select>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] text-gray-600 mb-1">
                Threshold{" "}
                <span className={mood ? "text-gray-300" : "text-gray-700"}>
                  {threshold.toFixed(2)}
                </span>
                {!mood && <span className="text-gray-700"> (no mood)</span>}
              </p>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={threshold}
                disabled={!mood}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                className="w-full mt-2 accent-violet-500 disabled:opacity-30"
              />
            </div>
          </div>
        </div>

        {/* Divider */}
        <div className="h-px md:h-auto md:w-px bg-gray-700 shrink-0" />

        {/* Section 3: Individual song overlay */}
        <div className="flex-1 min-w-0 px-4 py-3 bg-gray-900 rounded-b-lg md:rounded-bl-none md:rounded-r-lg" ref={dropRef}>
          <label className="block text-xs text-gray-500 mb-1.5 uppercase tracking-wider">
            Individual song overlay
          </label>
          <div className="relative">
            <input
              type="text"
              placeholder="Search song…"
              value={
                selectedSong
                  ? `${selectedSong.title ?? "?"} – ${selectedSong.artist ?? "?"}`
                  : search
              }
              onFocus={() => { setShowDrop(true); if (selectedSong) setSearch(""); }}
              onChange={(e) => { setSearch(e.target.value); setSongId(""); setShowDrop(true); }}
              className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 pr-6 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-violet-500"
            />
            {songId && (
              <button
                onClick={() => { setSongId(""); setSearch(""); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs"
              >
                ✕
              </button>
            )}
            {showDrop && !songId && (
              <div className="absolute z-20 left-0 right-0 top-full mt-1 bg-gray-900 border border-gray-700 rounded shadow-xl max-h-56 overflow-y-auto">
                {filteredSongs.length === 0 && (
                  <p className="px-3 py-2 text-xs text-gray-600">No matches</p>
                )}
                {filteredSongs.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => { setSongId(s.id); setSearch(""); setShowDrop(false); }}
                    className="w-full text-left px-3 py-2 text-xs text-gray-300 hover:bg-gray-800 truncate"
                  >
                    <span className="text-white">{s.title ?? "?"}</span>
                    <span className="text-gray-500"> – {s.artist ?? "?"}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-4 text-xs text-gray-600">
        {loading ? (
          <span className="text-gray-500">Loading…</span>
        ) : tsData ? (
          <>
            <span>
              <span className="text-gray-400">{tsData.song_count}</span> songs in avg
              {mood && (
                <span className="text-gray-600"> ({mood} ≥ {threshold.toFixed(2)})</span>
              )}
            </span>
            {tsData.selected_song && (
              <span className="text-violet-400">
                + {tsData.selected_song.title ?? "?"}{" "}
                ({formatTime(Math.round(tsData.selected_song.duration_seconds))})
              </span>
            )}
            {error && <span className="text-red-400">{error}</span>}
          </>
        ) : null}
      </div>

      {/* Chart */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 mb-3">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
            {featureLabel} — normalized (0–1)
          </p>
          <div className="flex rounded border border-gray-700 overflow-hidden text-xs">
            {MODE_OPTIONS.map((option) => (
              <button
                key={option.mode}
                onClick={() => setMode(option.mode)}
                className={`px-2.5 py-1 whitespace-nowrap transition-colors ${
                  mode === option.mode
                    ? "bg-violet-600 text-white"
                    : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        {chartData.length === 0 && !loading ? (
          <div className="flex items-center justify-center h-64 text-gray-600 text-sm">
            No timeseries data available for this selection.
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={340}>
              <ComposedChart
                data={chartData}
                margin={{ top: 4, right: 16, left: 0, bottom: 8 }}
              >
                <CartesianGrid {...GRID_STYLE} />
                <XAxis
                  dataKey="x"
                  type="number"
                  domain={[0, xAxisMax]}
                  ticks={xAxisTicks}
                  tickFormatter={formatX}
                  tick={AXIS_STYLE}
                />
                <YAxis tick={AXIS_STYLE} domain={[0, 1]} width={YAXIS_WIDTH} />
                <Tooltip content={renderTooltip} />
                <Area
                  type="monotone"
                  dataKey="band"
                  name="P25–P75"
                  stroke="none"
                  fill="#6b7280"
                  fillOpacity={0.25}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="avg"
                  name={`Group avg (${tsData?.song_count ?? 0} songs${mood ? ` · ${mood}≥${threshold.toFixed(2)}` : ""})`}
                  stroke="#6b7280"
                  strokeWidth={1.5}
                  strokeDasharray="5 3"
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
                {tsData?.selected_song && (
                  <Line
                    type="monotone"
                    dataKey="song"
                    name={tsData.selected_song.title ?? "Song"}
                    stroke="#818cf8"
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                    isAnimationActive={false}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>

            {tsData?.mode === "absolute" && (
              <>
                <ResponsiveContainer width="100%" height={COUNT_CHART_HEIGHT}>
                  <AreaChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
                    <XAxis
                      dataKey="x"
                      type="number"
                      domain={[0, xAxisMax]}
                      ticks={xAxisTicks}
                      tickFormatter={formatTime}
                      tick={AXIS_STYLE}
                    />
                    <YAxis tick={AXIS_STYLE} width={YAXIS_WIDTH} allowDecimals={false} />
                    <ReferenceLine y={tsData.min_songs} stroke="#4b5563" strokeDasharray="3 3" />
                    <Area
                      type="stepAfter"
                      dataKey="count"
                      stroke="#4b5563"
                      fill="#374151"
                      fillOpacity={0.4}
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
                <p className="text-[11px] text-gray-600" style={{ paddingLeft: YAXIS_WIDTH }}>
                  Active songs (n) over time — points with n &lt; {tsData.min_songs} are hidden
                </p>
              </>
            )}

            {/* Legend aligned at x=0 (YAxis width = 40px) */}
            <div className="flex flex-wrap gap-4 mt-1 text-xs text-gray-400" style={{ paddingLeft: YAXIS_WIDTH }}>
              <span className="flex items-center gap-1.5">
                <svg width="20" height="10">
                  <line x1="0" y1="5" x2="20" y2="5" stroke="#6b7280" strokeWidth="1.5" strokeDasharray="5 3" />
                </svg>
                Group avg (n = {tsData?.song_count ?? 0} songs
                {mood ? ` · ${mood}≥${threshold.toFixed(2)}` : ""})
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-5 h-2.5 rounded-sm bg-gray-500/25" />
                P25–P75
              </span>
              {tsData?.selected_song && (
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-5 h-0.5 bg-indigo-400 rounded" />
                  {tsData.selected_song.title ?? "Song"}
                </span>
              )}
            </div>
          </>
        )}
      </div>

      {/* Quick feature switcher */}
      <div className="space-y-2">
        <span className="text-xs text-gray-600">Quick switch:</span>
        <div className="space-y-1.5">
          {QUICK_GROUPS.map(({ group, labelCls, activeCls }) => (
            <div key={group} className="flex items-start gap-3 flex-wrap">
              <span className={`text-xs ${labelCls} w-20 shrink-0 pt-0.5 font-medium`}>
                {group}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {FEATURES.filter((f) => f.group === group).map((f) => (
                  <button
                    key={f.key}
                    title={f.tooltip}
                    onClick={() => setFeature(f.key)}
                    className={`px-2 py-0.5 rounded text-xs transition-colors ${
                      feature === f.key
                        ? activeCls
                        : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
