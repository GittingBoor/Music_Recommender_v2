import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ComposedChart, AreaChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from "recharts";
import type { TooltipProps } from "recharts";
import { fetchTimeseries } from "../../services/api";
import type { Song } from "../../types/song";
import type { TimeAxisMode, TimeseriesResponse } from "../../types/analysis";
import { COLOR, SERIES, gridProps, numericAxis, tooltipStyle } from "../../theme";

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

const QUICK_GROUPS = ["Mood", "ML Profile", "DSP"] as const;

const YAXIS_WIDTH = 40;
const COUNT_CHART_HEIGHT = 70;
const VALUE_DECIMALS = 3;
const RELATIVE_AXIS_MAX = 100;
const RELATIVE_TICK_STEP = 10;
const ABSOLUTE_TICK_STEP = 20;
const ABSOLUTE_AXIS_ROUNDING = 60;
const ABSOLUTE_STEP_SECONDS = 1;

/** Overlay songs are told apart by colour; the first keeps the signal colour. */
const OVERLAY_COLORS = [COLOR.signal, SERIES[0], SERIES[2]] as const;
const MAX_OVERLAY_SONGS = OVERLAY_COLORS.length;

type OverlayKey = `song${number}`;
const overlayKey = (index: number): OverlayKey => `song${index}`;

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
  count: number;
  /** song0 … songN: normalized values of the overlay songs. */
  [key: OverlayKey]: number | undefined;
}


interface Props {
  songs: Song[];
}

export function TimeseriesSection({ songs }: Props) {
  const [feature,   setFeature]   = useState("loudness");
  const [mood,      setMood]      = useState<string>("");
  const [threshold, setThreshold] = useState(0.7);
  const [overlays,  setOverlays]  = useState<{ id: string; color: string }[]>([]);
  const [search,    setSearch]    = useState("");
  const [showDrop,  setShowDrop]  = useState(false);
  const [mode,      setMode]      = useState<TimeAxisMode>("relative");

  const [tsData,  setTsData]  = useState<TimeseriesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  const dropRef = useRef<HTMLDivElement>(null);

  const songIds = useMemo(() => overlays.map((o) => o.id), [overlays]);

  // A song keeps its colour while it stays selected, even when others are removed.
  const colorOf = (id: string): string =>
    overlays.find((o) => o.id === id)?.color ?? OVERLAY_COLORS[0];

  const filteredSongs = useMemo(() => {
    const q = search.toLowerCase();
    return songs
      .filter(
        (s) =>
          (s.title?.toLowerCase().includes(q) || s.artist?.toLowerCase().includes(q)) &&
          !songIds.includes(s.id),
      )
      .slice(0, 30);
  }, [songs, search, songIds]);

  const selectedSongs = useMemo(
    () => songIds.map((id) => songs.find((s) => s.id === id)).filter((s): s is Song => s != null),
    [songs, songIds],
  );

  const canAddSong = songIds.length < MAX_OVERLAY_SONGS;

  const addSong = (id: string) => {
    setOverlays((prev) => {
      if (prev.length >= MAX_OVERLAY_SONGS || prev.some((o) => o.id === id)) return prev;
      const color = OVERLAY_COLORS.find((c) => !prev.some((o) => o.color === c)) ?? OVERLAY_COLORS[0];
      return [...prev, { id, color }];
    });
    setSearch("");
    setShowDrop(false);
  };

  const removeSong = (id: string) => setOverlays((prev) => prev.filter((o) => o.id !== id));

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchTimeseries(feature, mood || null, threshold, songIds, mode)
      .then(setTsData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [feature, mood, threshold, songIds, mode]);

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
    const overlaySongs = tsData.selected_songs;
    const len      = Math.max(tsData.positions.length, ...overlaySongs.map((o) => o.values.length));
    return Array.from({ length: len }, (_, i) => {
      const p25 = roundValue(tsData.p25_timeseries[i]);
      const p75 = roundValue(tsData.p75_timeseries[i]);
      const entry: ChartEntry = {
        x:     tsData.positions[i] ?? i * ABSOLUTE_STEP_SECONDS,
        avg:   roundValue(tsData.avg_timeseries[i]),
        band:  p25 != null && p75 != null ? [p25, p75] : undefined,
        count: tsData.counts_at_time[i] ?? 0,
      };
      overlaySongs.forEach((o, k) => { entry[overlayKey(k)] = roundValue(o.values[i]); });
      return entry;
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
        <div style={tooltipStyle} className="space-y-1">
          <p className="text-ink">{formatX((label as number) ?? 0)}</p>
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
          <p className="text-ink-3 text-2xs pt-1 border-t border-line-strong">
            {count} / {totalCount} songs active at this point
          </p>
        </div>
      );
    },
    [tsData, formatX],
  );

  return (
    <div className="max-w-7xl mx-auto px-4 pt-4 pb-16 md:px-6 md:pt-6 space-y-5">
      <div>
        <h2 className="t-section">
          Timeseries Analysis
        </h2>
        <p className="text-xs text-ink-3 mt-1.5">
          Compare individual songs against the normalized average of a filtered group.
          Y-axis is min-max normalized (0–1) per song/group.
        </p>
      </div>

      {/* Controls — three groups on one strip, divided by rules (stacked on phones) */}
      <div className="flex flex-col md:flex-row border-y border-line-strong text-sm">
        {/* Section 1: Feature */}
        <div className="flex-1 min-w-0 md:pr-5 py-3">
          <label className="block t-label mb-2">
            Feature
          </label>
          <select
            value={feature}
            onChange={(e) => setFeature(e.target.value)}
            className="field-select w-full"
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
        <div className="h-px md:h-auto md:w-px bg-line shrink-0" />

        {/* Section 2: Group avg filter */}
        <div className="flex-[2] min-w-0 md:px-5 py-3">
          <label className="block t-label mb-2">
            Group avg filter
          </label>
          <div className="flex gap-5 items-end">
            <div className="flex-1 min-w-0">
              <p className="text-xs text-ink-3 mb-1">Mood</p>
              <select
                value={mood}
                onChange={(e) => setMood(e.target.value)}
                className="field-select w-full"
              >
                <option value="">All songs</option>
                {MOODS.map((m) => (
                  <option key={m} value={m}>{m.charAt(0).toUpperCase() + m.slice(1)}</option>
                ))}
              </select>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-ink-3 mb-1">
                Threshold{" "}
                <span className={`font-mono text-2xs ${mood ? "text-ink" : "text-ink-4"}`}>
                  {threshold.toFixed(2)}
                </span>
                {!mood && <span className="text-ink-4"> (no mood)</span>}
              </p>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={threshold}
                disabled={!mood}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                className="range w-full h-8"
              />
            </div>
          </div>
        </div>

        {/* Divider */}
        <div className="h-px md:h-auto md:w-px bg-line shrink-0" />

        {/* Section 3: Individual song overlays (up to MAX_OVERLAY_SONGS) */}
        <div className="flex-1 min-w-0 md:pl-5 py-3" ref={dropRef}>
          <label className="block t-label mb-2">
            Song overlays{" "}
            <span className="font-mono text-ink-4">{songIds.length}/{MAX_OVERLAY_SONGS}</span>
          </label>
          {selectedSongs.length > 0 && (
            <ul className="mb-2 space-y-0.5">
              {selectedSongs.map((s) => (
                <li key={s.id} className="flex items-center gap-2 text-xs min-w-0">
                  <span
                    className="inline-block w-4 h-0.5 shrink-0"
                    style={{ backgroundColor: colorOf(s.id) }}
                  />
                  <span className="truncate flex-1 min-w-0">
                    <span className="text-ink">{s.title ?? "?"}</span>
                    <span className="text-ink-3"> – {s.artist ?? "?"}</span>
                  </span>
                  <button
                    onClick={() => removeSong(s.id)}
                    aria-label={`Remove ${s.title ?? "song"}`}
                    className="w-6 h-6 flex items-center justify-center text-ink-3 hover:text-ink shrink-0"
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
          {canAddSong && (
            <div className="relative">
              <input
                type="text"
                placeholder={songIds.length === 0 ? "Search song…" : "Add another song…"}
                value={search}
                onFocus={() => setShowDrop(true)}
                onChange={(e) => { setSearch(e.target.value); setShowDrop(true); }}
                className="field w-full"
              />
              {showDrop && (
                <div className="absolute z-20 left-0 right-0 top-full mt-1 bg-raised border border-line-strong rounded-sm max-h-56 overflow-y-auto">
                  {filteredSongs.length === 0 && (
                    <p className="px-3 py-2 font-mono text-2xs text-ink-3">No matches</p>
                  )}
                  {filteredSongs.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => addSong(s.id)}
                      className="w-full text-left px-3 py-2 text-xs text-ink-2 hover:bg-line truncate border-b border-line last:border-b-0"
                    >
                      <span className="text-ink">{s.title ?? "?"}</span>
                      <span className="text-ink-3"> – {s.artist ?? "?"}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-4 font-mono text-2xs text-ink-3 h-4">
        {loading ? (
          <span>Loading…</span>
        ) : tsData ? (
          <>
            <span>
              <span className="text-ink">{tsData.song_count}</span> songs in avg
              {mood && (
                <span> ({mood} ≥ {threshold.toFixed(2)})</span>
              )}
            </span>
            {tsData.selected_songs.map((o) => (
              <span key={o.song_id} className="truncate" style={{ color: colorOf(o.song_id) }}>
                + {o.title ?? "?"} ({formatTime(Math.round(o.duration_seconds))})
              </span>
            ))}
            {error && <span className="text-bad">{error}</span>}
          </>
        ) : null}
      </div>

      {/* Chart */}
      <div>
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 mb-4">
          <p className="flex items-baseline gap-2">
            <span className="text-md font-semibold text-ink stretch-semi">{featureLabel}</span>
            <span className="t-label">normalized (0–1)</span>
          </p>
          <div className="seg">
            {MODE_OPTIONS.map((option) => (
              <button
                key={option.mode}
                onClick={() => setMode(option.mode)}
                aria-pressed={mode === option.mode}
                className={`seg-item ${mode === option.mode ? "seg-item-on" : ""}`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        {chartData.length === 0 && !loading ? (
          <div className="flex items-center justify-center h-64 font-mono text-xs text-ink-3">
            No timeseries data available for this selection.
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={340}>
              <ComposedChart
                data={chartData}
                margin={{ top: 4, right: 16, left: 0, bottom: 8 }}
              >
                <CartesianGrid {...gridProps} vertical={false} />
                <XAxis
                  dataKey="x"
                  type="number"
                  domain={[0, xAxisMax]}
                  ticks={xAxisTicks}
                  tickFormatter={formatX}
                  {...numericAxis}
                />
                <YAxis {...numericAxis} axisLine={false} domain={[0, 1]} width={YAXIS_WIDTH} />
                <Tooltip content={renderTooltip} />
                <Area
                  type="monotone"
                  dataKey="band"
                  name="P25–P75"
                  stroke="none"
                  fill={COLOR.ink3}
                  fillOpacity={0.18}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="avg"
                  name={`Group avg (${tsData?.song_count ?? 0} songs${mood ? ` · ${mood}≥${threshold.toFixed(2)}` : ""})`}
                  stroke={COLOR.ink2}
                  strokeWidth={1.5}
                  strokeDasharray="5 3"
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
                {tsData?.selected_songs.map((o, k) => (
                  <Line
                    key={o.song_id}
                    type="monotone"
                    dataKey={overlayKey(k)}
                    name={o.title ?? "Song"}
                    stroke={colorOf(o.song_id)}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                    isAnimationActive={false}
                  />
                ))}
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
                      {...numericAxis}
                    />
                    <YAxis {...numericAxis} axisLine={false} width={YAXIS_WIDTH} allowDecimals={false} />
                    <ReferenceLine y={tsData.min_songs} stroke={COLOR.ink4} strokeDasharray="3 3" />
                    <Area
                      type="stepAfter"
                      dataKey="count"
                      stroke={COLOR.ink4}
                      fill={COLOR.ink4}
                      fillOpacity={0.25}
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
                <p className="font-mono text-2xs text-ink-3" style={{ paddingLeft: YAXIS_WIDTH }}>
                  Active songs (n) over time — points with n &lt; {tsData.min_songs} are hidden
                </p>
              </>
            )}

            {/* Legend aligned at x=0 (YAxis width = 40px) */}
            <div className="flex flex-wrap gap-5 mt-2 text-xs text-ink-2" style={{ paddingLeft: YAXIS_WIDTH }}>
              <span className="flex items-center gap-1.5">
                <svg width="20" height="10">
                  <line x1="0" y1="5" x2="20" y2="5" stroke={COLOR.ink2} strokeWidth="1.5" strokeDasharray="5 3" />
                </svg>
                Group avg (n = {tsData?.song_count ?? 0} songs
                {mood ? ` · ${mood}≥${threshold.toFixed(2)}` : ""})
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-5 h-2.5 bg-ink-3/20" />
                P25–P75
              </span>
              {tsData?.selected_songs.map((o) => (
                <span key={o.song_id} className="flex items-center gap-1.5">
                  <span className="inline-block w-5 h-0.5" style={{ backgroundColor: colorOf(o.song_id) }} />
                  {o.title ?? "Song"}
                </span>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Quick feature switcher */}
      <div className="space-y-2 pt-4 border-t border-line">
        <span className="t-label">Quick switch:</span>
        <div className="space-y-1">
          {QUICK_GROUPS.map((group) => (
            <div key={group} className="flex items-start gap-3 flex-wrap">
              <span className="text-xs text-ink-3 w-20 shrink-0 pt-[3px]">
                {group}
              </span>
              <div className="flex flex-wrap gap-x-1 gap-y-0.5">
                {FEATURES.filter((f) => f.group === group).map((f) => (
                  <button
                    key={f.key}
                    title={f.tooltip}
                    onClick={() => setFeature(f.key)}
                    aria-pressed={feature === f.key}
                    className={`px-2 h-6 rounded-sm text-xs ${
                      feature === f.key
                        ? "bg-ink text-ground"
                        : "text-ink-2 hover:text-ink hover:bg-raised"
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
