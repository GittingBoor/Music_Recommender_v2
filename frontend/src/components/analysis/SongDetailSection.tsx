import { useEffect, useMemo, useRef, useState } from "react";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
  PieChart, Pie,
  LineChart, Line,
} from "recharts";
import { fetchSongDetail } from "../../services/api";
import type { Song } from "../../types/song";
import type { SongDetail } from "../../types/analysis";

const TOOLTIP_STYLE = {
  backgroundColor: "#111827",
  border: "1px solid #374151",
  borderRadius: 6,
  color: "#f3f4f6",
  fontSize: 12,
};
const AXIS_STYLE = { fill: "#6b7280", fontSize: 11 };
const GRID_STYLE = { stroke: "#1f2937" };
const TOOLTIP_LABEL = { color: "#f3f4f6" };
const TOOLTIP_ITEM  = { color: "#e5e7eb" };

const MOOD_COLORS: Record<string, string> = {
  happy:      "#fbbf24",
  sad:        "#60a5fa",
  aggressive: "#f87171",
  party:      "#e879f9",
  relaxed:    "#34d399",
  acoustic:   "#a78bfa",
  electronic: "#2dd4bf",
};

const TS_COLORS: Record<string, string> = {
  loudness:           "#60a5fa",
  spectral_centroid:  "#34d399",
  spectral_rolloff:   "#fbbf24",
  spectral_flux:      "#f87171",
  zero_crossing_rate: "#a78bfa",
  dissonance:         "#f472b6",
  arousal:            "#fb923c",
  valence:            "#38bdf8",
  approachability:    "#818cf8",
  engagement:         "#4ade80",
  voice:              "#2dd4bf",
  gender:             "#e879f9",
  happy:              "#fbbf24",
  sad:                "#60a5fa",
  aggressive:         "#f87171",
  party:              "#e879f9",
  relaxed:            "#34d399",
  acoustic:           "#a78bfa",
  electronic:         "#2dd4bf",
};

const TS_LABEL: Record<string, string> = {
  loudness: "Loudness", spectral_centroid: "Spec. Centroid",
  spectral_rolloff: "Spec. Rolloff", spectral_flux: "Spec. Flux",
  zero_crossing_rate: "ZCR", dissonance: "Dissonance",
  arousal: "Arousal", valence: "Valence",
  approachability: "Approachability", engagement: "Engagement",
  voice: "Voice", gender: "Gender",
  happy: "Happy", sad: "Sad", aggressive: "Aggressive",
  party: "Party", relaxed: "Relaxed", acoustic: "Acoustic", electronic: "Electronic",
};

const GENRE_COLORS = [
  "#818cf8","#60a5fa","#34d399","#fbbf24","#f87171",
  "#a78bfa","#2dd4bf","#fb923c","#e879f9","#4ade80",
];

function fmt(s: number | null | undefined) {
  if (s == null) return "–";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function normalizeArray(vals: number[]): number[] {
  const mn = Math.min(...vals);
  const mx = Math.max(...vals);
  if (mx === mn) return vals.map(() => 0.5);
  return vals.map((v) => parseFloat(((v - mn) / (mx - mn)).toFixed(4)));
}

// Arousal/valence are raw MusiCNN regression outputs on a 1–9 scale (emomusic).
function normalizeAV(v: number): number {
  return Math.max(0, Math.min(1, (v - 1) / 8));
}


function ChartCard({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-gray-900 border border-gray-800 rounded-lg p-4 ${className}`}>
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">{title}</p>
      {children}
    </div>
  );
}

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center bg-gray-800 rounded-lg px-4 py-2 min-w-0">
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-base font-bold text-white mt-0.5 truncate">{value}</span>
    </div>
  );
}

function DualBar({ leftLabel, leftVal, rightLabel, rightVal, leftColor, rightColor }: {
  leftLabel: string; leftVal: number; rightLabel: string; rightVal: number;
  leftColor: string; rightColor: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500 w-20 text-right truncate">{leftLabel}</span>
        <div className="flex-1 flex h-4 rounded overflow-hidden bg-gray-800 gap-px">
          <div className="h-full transition-all" style={{ width: `${leftVal * 100}%`, background: leftColor }} />
        </div>
        <span className="text-xs font-mono text-gray-400 w-10">{(leftVal * 100).toFixed(0)}%</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500 w-20 text-right truncate">{rightLabel}</span>
        <div className="flex-1 flex h-4 rounded overflow-hidden bg-gray-800">
          <div className="h-full transition-all" style={{ width: `${rightVal * 100}%`, background: rightColor }} />
        </div>
        <span className="text-xs font-mono text-gray-400 w-10">{(rightVal * 100).toFixed(0)}%</span>
      </div>
    </div>
  );
}

interface Props {
  songs: Song[];
}

export function SongDetailSection({ songs }: Props) {
  const [search,       setSearch]       = useState("");
  const [showDrop,     setShowDrop]     = useState(false);
  const [selectedId,   setSelectedId]   = useState<string>("");
  const [detail,       setDetail]       = useState<SongDetail | null>(null);
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState<string | null>(null);
  const [visibleTs,    setVisibleTs]    = useState<Set<string>>(
    new Set(["loudness", "arousal", "valence", "happy"]),
  );
  const dropRef = useRef<HTMLDivElement>(null);

  const filteredSongs = useMemo(() => {
    const q = search.toLowerCase();
    return songs
      .filter((s) => s.title?.toLowerCase().includes(q) || s.artist?.toLowerCase().includes(q))
      .slice(0, 40);
  }, [songs, search]);

  const selectedSong = useMemo(() => songs.find((s) => s.id === selectedId) ?? null, [songs, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    fetchSongDetail(selectedId)
      .then(setDetail)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedId]);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) {
        setShowDrop(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  // Build timeseries chart data.
  // DSP/EffNet features are 1 sample/second; MusiCNN (arousal, valence) are 1 sample/~3s.
  // Scale MusiCNN indices so both span the full song duration on the x-axis.
  const tsChartData = useMemo(() => {
    if (!detail) return [];
    const ts = detail.timeseries;
    const keysWithData = [...visibleTs].filter((k) => {
      const arr = ts[k as keyof typeof ts];
      return Array.isArray(arr) && arr.length > 0;
    });
    if (!keysWithData.length) return [];

    const normalized: Record<string, number[]> = {};
    let maxLen = 0;
    for (const k of keysWithData) {
      const arr = ts[k as keyof typeof ts] as number[];
      normalized[k] = normalizeArray(arr);
      maxLen = Math.max(maxLen, arr.length);
    }
    // Proportionally stretch all features to maxLen so every series spans the full x-axis.
    return Array.from({ length: maxLen }, (_, sec) => {
      const row: Record<string, number | undefined> = { sec };
      for (const k of keysWithData) {
        const len = normalized[k].length;
        const idx = Math.min(Math.round((sec * len) / maxLen), len - 1);
        row[k] = normalized[k][idx];
      }
      return row;
    });
  }, [detail, visibleTs]);

  const toggleTs = (key: string) => {
    setVisibleTs((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Mood data for radar
  const moodRadarData = detail?.ml_moods
    ? Object.entries(detail.ml_moods).map(([key, val]) => ({
        subject: key,
        value: val ?? 0,
      }))
    : [];

  // Instruments data
  const instrData = (detail?.instruments ?? [])
    .sort((a, b) => b.probability - a.probability)
    .slice(0, 12);

  // Parent genres data for pie
  const genreData = (detail?.parent_genres ?? []).sort((a, b) => b.percentage - a.percentage);

  // All TS keys available
  const allTsKeys = detail
    ? (Object.keys(detail.timeseries) as string[]).filter((k) => {
        const arr = detail.timeseries[k as keyof typeof detail.timeseries];
        return Array.isArray(arr) && arr.length > 0;
      })
    : [];

  return (
    <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">

      {/* Search bar */}
      <div>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Song Detail
        </h2>
        <div className="relative max-w-lg" ref={dropRef}>
          <input
            type="text"
            placeholder="Search for a song by title or artist…"
            value={selectedSong && !showDrop
              ? `${selectedSong.title ?? "?"} – ${selectedSong.artist ?? "?"}`
              : search}
            onFocus={() => { setShowDrop(true); if (selectedSong) setSearch(""); }}
            onChange={(e) => { setSearch(e.target.value); setSelectedId(""); setShowDrop(true); }}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-violet-500"
          />
          {selectedId && (
            <button
              onClick={() => { setSelectedId(""); setSearch(""); setDetail(null); }}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs"
            >
              ✕
            </button>
          )}
          {showDrop && (
            <div className="absolute z-20 top-full left-0 right-0 mt-1 bg-gray-900 border border-gray-700 rounded-lg shadow-xl max-h-64 overflow-y-auto">
              {filteredSongs.length === 0 && (
                <p className="px-4 py-3 text-xs text-gray-600">No songs match</p>
              )}
              {filteredSongs.map((s) => (
                <button
                  key={s.id}
                  onClick={() => { setSelectedId(s.id); setSearch(""); setShowDrop(false); }}
                  className="w-full text-left px-4 py-2.5 text-sm hover:bg-gray-800 flex flex-col"
                >
                  <span className="text-gray-100 font-medium truncate">{s.title ?? "Unknown"}</span>
                  <span className="text-gray-500 text-xs truncate">{s.artist ?? "Unknown artist"}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Empty state */}
      {!selectedId && (
        <div className="flex items-center justify-center h-48 text-gray-600 text-sm border border-dashed border-gray-800 rounded-lg">
          Select a song above to see its detailed analysis
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-48 text-gray-500 text-sm">
          Loading…
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="text-red-400 text-sm p-4 bg-red-950 border border-red-800 rounded-lg">
          {error}
        </div>
      )}

      {/* Detail view */}
      {detail && !loading && (
        <div className="space-y-5">

          {/* Header */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
            <h3 className="text-xl font-bold text-white truncate">{detail.title ?? "Unknown"}</h3>
            <p className="text-gray-400 text-sm mt-0.5 truncate">{detail.artist ?? "Unknown artist"}</p>
            <div className="flex flex-wrap gap-2 mt-3">
              {detail.file_metadata?.duration_seconds != null && (
                <StatPill label="Duration" value={fmt(detail.file_metadata.duration_seconds)} />
              )}
              {detail.track_metadata?.release_date && (
                <StatPill label="Released" value={detail.track_metadata.release_date.slice(0, 4)} />
              )}
              {detail.track_metadata?.playcount != null && (
                <StatPill label="Last.fm Plays" value={detail.track_metadata.playcount.toLocaleString()} />
              )}
              {detail.dsp?.danceability != null && (
                <StatPill label="Danceability" value={`${(detail.dsp.danceability * 100).toFixed(0)}%`} />
              )}
            </div>
          </div>

          {/* Mood + Profile */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

            <ChartCard title="Mood Profile">
              <ResponsiveContainer width="100%" height={260}>
                <RadarChart data={moodRadarData} margin={{ top: 30, right: 55, bottom: 30, left: 55 }}>
                  <PolarGrid stroke="#1f2937" />
                  <PolarAngleAxis
                    dataKey="subject"
                    tick={(props: Record<string, unknown>) => {
                      const x = props.x as number;
                      const y = props.y as number;
                      const cx = (props.cx as number | undefined) ?? 0;
                      const cy = (props.cy as number | undefined) ?? 0;
                      const payload = props.payload as { value: string };
                      const val = moodRadarData.find((d) => d.subject === payload.value)?.value ?? 0;
                      // Push label outward 18px from its default position
                      const dx = x - cx;
                      const dy = y - cy;
                      const len = Math.sqrt(dx * dx + dy * dy) || 1;
                      const nx = x + (dx / len) * 18;
                      const ny = y + (dy / len) * 18;
                      return (
                        <g>
                          <text
                            x={nx}
                            y={ny}
                            textAnchor="middle"
                            dominantBaseline="central"
                            fill={MOOD_COLORS[payload.value] ?? "#9ca3af"}
                            fontSize={11}
                            fontWeight={600}
                          >
                            {payload.value}
                          </text>
                          <text
                            x={nx}
                            y={ny + 14}
                            textAnchor="middle"
                            fill="#6b7280"
                            fontSize={9}
                          >
                            {(val * 100).toFixed(0)}%
                          </text>
                        </g>
                      );
                    }}
                  />
                  <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
                  <Radar
                    dataKey="value"
                    fill="#fbbf24"
                    fillOpacity={0.25}
                    stroke="#fbbf24"
                    strokeWidth={2}
                    activeDot={false}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="ML Profile Scores">
              {detail.ml_profile ? (
                <div className="space-y-3 pt-1">
                  <DualBar
                    leftLabel="Niche"
                    leftVal={detail.ml_profile.niche_score ?? 0}
                    rightLabel="Mainstream"
                    rightVal={detail.ml_profile.mainstream_score ?? 0}
                    leftColor="#818cf8"
                    rightColor="#60a5fa"
                  />
                  <DualBar
                    leftLabel="Background"
                    leftVal={detail.ml_profile.background_score ?? 0}
                    rightLabel="Active"
                    rightVal={detail.ml_profile.active_score ?? 0}
                    leftColor="#6b7280"
                    rightColor="#34d399"
                  />
                  <DualBar
                    leftLabel="Instrumental"
                    leftVal={detail.ml_profile.instrumental_score ?? 0}
                    rightLabel="Vocal"
                    rightVal={detail.ml_profile.vocal_score ?? 0}
                    leftColor="#a78bfa"
                    rightColor="#2dd4bf"
                  />
                  <DualBar
                    leftLabel="Female"
                    leftVal={detail.ml_profile.female_score ?? 0}
                    rightLabel="Male"
                    rightVal={detail.ml_profile.male_score ?? 0}
                    leftColor="#f472b6"
                    rightColor="#60a5fa"
                  />
                  <div className="grid grid-cols-2 gap-2 pt-2">
                    <div className="bg-gray-800 rounded p-3">
                      <p className="text-xs text-gray-500">Arousal</p>
                      <div className="mt-1 h-2 bg-gray-700 rounded overflow-hidden">
                        <div
                          className="h-full bg-orange-400 rounded transition-all"
                          style={{ width: `${normalizeAV(detail.ml_profile.arousal ?? 1) * 100}%` }}
                        />
                      </div>
                      <p className="text-sm font-mono font-bold text-orange-400 mt-1">
                        {(normalizeAV(detail.ml_profile.arousal ?? 1) * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div className="bg-gray-800 rounded p-3">
                      <p className="text-xs text-gray-500">Valence</p>
                      <div className="mt-1 h-2 bg-gray-700 rounded overflow-hidden">
                        <div
                          className="h-full bg-sky-400 rounded transition-all"
                          style={{ width: `${normalizeAV(detail.ml_profile.valence ?? 1) * 100}%` }}
                        />
                      </div>
                      <p className="text-sm font-mono font-bold text-sky-400 mt-1">
                        {(normalizeAV(detail.ml_profile.valence ?? 1) * 100).toFixed(1)}%
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-gray-600 text-xs">No ML profile data</p>
              )}
            </ChartCard>
          </div>

          {/* Genres + Instruments */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

            <ChartCard title="Genre Distribution">
              {genreData.length > 0 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie
                      data={genreData}
                      dataKey="percentage"
                      nameKey="genre"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      innerRadius={30}
                      labelLine={false}
                      label={(props: Record<string, unknown>) => {
                        const percent = props.percent as number;
                        if (percent <= 0.05) return null;
                        const cx = props.cx as number;
                        const cy = props.cy as number;
                        const midAngle = props.midAngle as number;
                        const outerRadius = props.outerRadius as number;
                        const genre = props.genre as string;
                        const RADIAN = Math.PI / 180;
                        const radius = outerRadius + 22;
                        const lx = cx + radius * Math.cos(-midAngle * RADIAN);
                        const ly = cy + radius * Math.sin(-midAngle * RADIAN);
                        return (
                          <text
                            x={lx}
                            y={ly}
                            fill="#9ca3af"
                            textAnchor={lx > cx ? "start" : "end"}
                            dominantBaseline="central"
                            fontSize={10}
                          >
                            {genre} {(percent * 100).toFixed(0)}%
                          </text>
                        );
                      }}
                    >
                      {genreData.map((_, i) => (
                        <Cell key={i} fill={GENRE_COLORS[i % GENRE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM}
                      formatter={(v) => [`${(v as number).toFixed(1)}%`, "share"]}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-gray-600 text-xs pt-2">No genre data</p>
              )}
            </ChartCard>

            <ChartCard title="Top Instruments">
              {instrData.length > 0 ? (
                <ResponsiveContainer width="100%" height={Math.max(180, instrData.length * 26)}>
                  <BarChart
                    data={instrData}
                    layout="vertical"
                    margin={{ top: 0, right: 50, left: 8, bottom: 0 }}
                  >
                    <CartesianGrid {...GRID_STYLE} horizontal={false} />
                    <XAxis type="number" tick={AXIS_STYLE} domain={[0, 1]} />
                    <YAxis
                      type="category"
                      dataKey="instrument"
                      tick={{ fill: "#9ca3af", fontSize: 11 }}
                      width={100}
                    />
                    <Tooltip
                      contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM}
                      formatter={(v) => [(v as number).toFixed(3), "probability"]}
                    />
                    <Bar dataKey="probability" radius={[0, 3, 3, 0]}>
                      {instrData.map((_, i) => (
                        <Cell key={i} fill={GENRE_COLORS[i % GENRE_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-gray-600 text-xs pt-2">No instrument data</p>
              )}
            </ChartCard>
          </div>

          {/* Audio details */}
          {detail.dsp && (
            <ChartCard title="Audio Details">
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                {[
                  { label: "BPM",           val: detail.dsp.bpm?.toFixed(1) },
                  { label: "Beat Confidence", val: detail.dsp.beat_confidence ? `${(detail.dsp.beat_confidence * 100).toFixed(0)}%` : null },
                  { label: "Key",           val: detail.dsp.key ? `${detail.dsp.key} ${detail.dsp.scale}` : null },
                  { label: "Key Strength",  val: detail.dsp.key_strength?.toFixed(3) },
                  { label: "Tuning Hz",     val: detail.dsp.tuning_frequency_hz?.toFixed(1) },
                  { label: "LUFS",          val: detail.dsp.integrated_lufs?.toFixed(1) },
                  { label: "Loudness dB",   val: detail.dsp.loudness_db?.toFixed(1) },
                  { label: "Dyn. Complexity", val: detail.dsp.dynamic_complexity?.toFixed(3) },
                  { label: "Dissonance",    val: detail.dsp.dissonance?.toFixed(3) },
                  { label: "Spec. Centroid", val: detail.dsp.spectral_centroid_mean?.toFixed(0) },
                  { label: "Chord Change",  val: detail.dsp.chord_change_rate?.toFixed(3) },
                  { label: "Top Chord",     val: detail.dsp.most_common_chord },
                ].map(({ label, val }) => (
                  val != null ? (
                    <div key={label} className="bg-gray-800 rounded p-2">
                      <p className="text-xs text-gray-500">{label}</p>
                      <p className="text-sm font-mono font-bold text-gray-100 mt-0.5">{val}</p>
                    </div>
                  ) : null
                ))}
              </div>
            </ChartCard>
          )}

          {/* Timeseries */}
          <ChartCard title="Feature Timeseries">
            {/* Toggle buttons */}
            <div className="flex flex-wrap gap-1.5 mb-4">
              {allTsKeys.map((k) => (
                <button
                  key={k}
                  onClick={() => toggleTs(k)}
                  className="px-2 py-0.5 rounded text-xs transition-colors border"
                  style={{
                    borderColor: visibleTs.has(k) ? (TS_COLORS[k] ?? "#818cf8") : "#374151",
                    color:       visibleTs.has(k) ? (TS_COLORS[k] ?? "#818cf8") : "#6b7280",
                    background:  visibleTs.has(k) ? `${TS_COLORS[k] ?? "#818cf8"}15` : "transparent",
                  }}
                >
                  {TS_LABEL[k] ?? k}
                </button>
              ))}
            </div>

            {tsChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={tsChartData} margin={{ top: 4, right: 16, left: -16, bottom: 8 }}>
                  <CartesianGrid {...GRID_STYLE} />
                  <XAxis
                    dataKey="sec"
                    tick={AXIS_STYLE}
                    label={{ value: "seconds", position: "insideBottom", offset: -4, fill: "#6b7280", fontSize: 10 }}
                  />
                  <YAxis tick={AXIS_STYLE} domain={[0, 1]} />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM}
                    labelFormatter={(l) => `${l}s`}
                    formatter={(v, name) => [
                      typeof v === "number" ? v.toFixed(3) : v,
                      TS_LABEL[name as string] ?? name,
                    ]}
                  />
                  {[...visibleTs].map((k) => (
                    <Line
                      key={k}
                      type="monotone"
                      dataKey={k}
                      stroke={TS_COLORS[k] ?? "#818cf8"}
                      strokeWidth={1.5}
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-48 text-gray-600 text-sm">
                Select at least one feature above
              </div>
            )}
          </ChartCard>

        </div>
      )}
    </div>
  );
}
