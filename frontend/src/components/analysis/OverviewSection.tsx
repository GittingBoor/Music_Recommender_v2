import { useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from "recharts";
import type { Song } from "../../types/song";

const COLORS = [
  "#818cf8","#60a5fa","#34d399","#fbbf24","#f87171",
  "#a78bfa","#2dd4bf","#fb923c","#e879f9","#4ade80",
  "#f472b6","#38bdf8","#facc15","#86efac","#c084fc",
];

const MOOD_COLORS: Record<string, string> = {
  happy:      "#fbbf24",
  sad:        "#60a5fa",
  aggressive: "#f87171",
  party:      "#e879f9",
  relaxed:    "#34d399",
  acoustic:   "#a78bfa",
  electronic: "#2dd4bf",
};

type InstrumentCategory =
  | "percussion" | "bass" | "guitar" | "piano"
  | "strings" | "brass" | "woodwind" | "voice" | "synth" | "other";

const INSTRUMENT_CATEGORY_DEFS: Array<{ key: InstrumentCategory; label: string; keywords: string[]; palette: readonly string[] }> = [
  { key: "percussion", label: "Percussion / Drums",   keywords: ["drum","percussion","cymbal","hi-hat","snare","kick","tom","clap"],                     palette: ["#fb923c","#f97316","#ea580c","#c2410c","#fdba74","#fed7aa"] },
  { key: "bass",       label: "Bass",                 keywords: ["bass"],                                                                                palette: ["#818cf8","#6366f1","#4f46e5","#3730a3","#a5b4fc","#c7d2fe"] },
  { key: "guitar",     label: "Guitar family",        keywords: ["guitar","banjo","ukulele","mandolin","sitar","lute"],                                   palette: ["#34d399","#10b981","#059669","#047857","#6ee7b7","#a7f3d0"] },
  { key: "piano",      label: "Piano / Keys",         keywords: ["piano","keyboard","organ","harpsichord","accordion","celesta"],                         palette: ["#c084fc","#a855f7","#9333ea","#7e22ce","#d8b4fe","#e9d5ff"] },
  { key: "strings",    label: "Orchestral strings",   keywords: ["violin","cello","viola","string","harp","fiddle","contrabass"],                         palette: ["#4ade80","#22c55e","#16a34a","#15803d","#86efac","#bbf7d0"] },
  { key: "brass",      label: "Brass",                keywords: ["trumpet","trombone","tuba","horn","brass","cornet","flugelhorn"],                       palette: ["#fbbf24","#f59e0b","#d97706","#b45309","#fde68a","#fef3c7"] },
  { key: "woodwind",   label: "Woodwind",             keywords: ["saxophone","flute","clarinet","oboe","bassoon","wind","piccolo"],                       palette: ["#facc15","#eab308","#ca8a04","#a16207","#fef08a","#fef9c3"] },
  { key: "voice",      label: "Voice / Vocals",       keywords: ["voice","vocal","choir","singing","chant"],                                              palette: ["#fb7185","#f43f5e","#e11d48","#be123c","#fda4af","#fecdd3"] },
  { key: "synth",      label: "Electronic / Synth",   keywords: ["synth","electronic","sampler","theremin"],                                              palette: ["#22d3ee","#06b6d4","#0891b2","#0e7490","#67e8f9","#a5f3fc"] },
  { key: "other",      label: "Other",                keywords: [],                                                                                      palette: ["#9ca3af","#6b7280","#4b5563","#374151","#d1d5db","#e5e7eb"] },
];

const CATEGORY_ORDER = INSTRUMENT_CATEGORY_DEFS.map((c) => c.key);

function classifyInstrument(name: string): InstrumentCategory {
  const n = name.toLowerCase();
  for (const def of INSTRUMENT_CATEGORY_DEFS) {
    if (def.keywords.some((k) => n.includes(k))) return def.key;
  }
  return "other";
}

const AXIS_STYLE = { fill: "#6b7280", fontSize: 11 };
const GRID_STYLE = { stroke: "#1f2937" };
const TOOLTIP_STYLE = {
  backgroundColor: "#111827",
  border: "1px solid #374151",
  borderRadius: 6,
  color: "#f3f4f6",
  fontSize: 12,
};
const TOOLTIP_LABEL  = { color: "#f3f4f6" };
const TOOLTIP_ITEM   = { color: "#e5e7eb" };

function ChartCard({ title, children, className = "" }: {
  title: string; children: React.ReactNode; className?: string;
}) {
  return (
    <div className={`bg-gray-900 border border-gray-800 rounded-lg p-4 ${className}`}>
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">{title}</p>
      {children}
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-2xl font-bold text-white mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  );
}

function makeHistogram(values: number[], bins: number) {
  if (!values.length) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const step = (max - min) / bins || 1;
  const result = Array.from({ length: bins }, (_, i) => ({
    label: `${(min + i * step).toFixed(0)}`,
    count: 0,
    min: min + i * step,
    max: min + (i + 1) * step,
  }));
  for (const v of values) {
    const idx = Math.min(Math.floor((v - min) / step), bins - 1);
    result[idx].count++;
  }
  return result;
}

function fmt(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

interface Props { songs: Song[]; }

export function OverviewSection({ songs }: Props) {
  const data = useMemo(() => {
    const hasDsp     = songs.filter((s) => s.dsp_features);
    const hasMoods   = songs.filter((s) => s.ml_moods);
    const hasMeta    = songs.filter((s) => s.file_metadata);
    const hasTrack   = songs.filter((s) => s.track_metadata);

    // Total hours
    const totalSeconds = hasMeta.reduce(
      (sum, s) => sum + (s.file_metadata!.duration_seconds ?? 0), 0,
    );
    const totalHours = totalSeconds / 3600;

    // BPM histogram
    const bpms = hasDsp.map((s) => s.dsp_features!.bpm!).filter((v) => v != null);
    const bpmHist = makeHistogram(bpms, 18);

    // Duration histogram
    const durations = hasMeta.map((s) => s.file_metadata!.duration_seconds!).filter((v) => v != null);
    const durHist = makeHistogram(durations, 14);

    // Danceability histogram
    const danceVals = hasDsp.map((s) => s.dsp_features!.danceability!).filter((v) => v != null);
    const danceHist = makeHistogram(danceVals, 14);

    // Key distribution (radar)
    const KEY_ORDER = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
    const keyCounts: Record<string, number> = {};
    for (const s of hasDsp) {
      const k = s.dsp_features?.key;
      if (k) keyCounts[k] = (keyCounts[k] ?? 0) + 1;
    }
    const keyData = KEY_ORDER.map((k) => ({ subject: k, value: keyCounts[k] ?? 0 }));

    // Major / Minor
    const scaleCounts: Record<string, number> = {};
    for (const s of hasDsp) {
      const sc = s.dsp_features?.scale;
      if (sc) scaleCounts[sc] = (scaleCounts[sc] ?? 0) + 1;
    }
    const scaleData = Object.entries(scaleCounts).map(([name, value]) => ({ name, value }));

    // Dominant mood per song
    const dominantMoodCounts: Record<string, number> = {};
    for (const s of hasMoods) {
      const m = s.ml_moods!;
      const entries = (Object.entries(m) as [string, number | null][]).filter(([, v]) => v != null) as [string, number][];
      if (!entries.length) continue;
      const dominant = entries.sort(([, a], [, b]) => b - a)[0][0];
      dominantMoodCounts[dominant] = (dominantMoodCounts[dominant] ?? 0) + 1;
    }
    const dominantMoodData = Object.entries(dominantMoodCounts)
      .sort(([, a], [, b]) => b - a)
      .map(([mood, count]) => ({ mood, count }));

    // Release years — fill every year from min to max so axis is continuous
    const yearCounts: Record<number, number> = {};
    for (const s of hasTrack) {
      const rd = s.track_metadata?.release_date;
      if (!rd) continue;
      const y = parseInt(rd.slice(0, 4), 10);
      if (!isNaN(y) && y > 1900 && y <= 2030) yearCounts[y] = (yearCounts[y] ?? 0) + 1;
    }
    const yearKeys = Object.keys(yearCounts).map(Number);
    const releaseYears =
      yearKeys.length === 0
        ? []
        : (() => {
            const mn = Math.min(...yearKeys);
            const mx = Math.max(...yearKeys);
            return Array.from({ length: mx - mn + 1 }, (_, i) => ({
              year: mn + i,
              count: yearCounts[mn + i] ?? 0,
            }));
          })();
    const yearDomain: [number, number] | undefined =
      releaseYears.length >= 2
        ? [releaseYears[0].year, releaseYears[releaseYears.length - 1].year]
        : undefined;
    const yearTicks: number[] = (() => {
      if (!yearDomain) return [];
      const [mn, mx] = yearDomain;
      const span = mx - mn;
      const step = span <= 10 ? 1 : span <= 20 ? 2 : span <= 40 ? 5 : 10;
      const start = Math.ceil(mn / step) * step;
      const ticks: number[] = [];
      for (let y = start; y <= mx; y += step) ticks.push(y);
      return ticks;
    })();

    // Top artists by song count
    const artistCounts: Record<string, number> = {};
    for (const s of songs) {
      const a = s.artist ?? "Unknown";
      artistCounts[a] = (artistCounts[a] ?? 0) + 1;
    }
    const topArtists = Object.entries(artistCounts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 15)
      .map(([name, count]) => ({ name, count }));

    // Parent genres: top 3 per song → count how many songs feature each genre
    const parentGenreCounts: Record<string, number> = {};
    for (const s of songs) {
      const top3 = [...s.parent_genres]
        .sort((a, b) => b.percentage - a.percentage)
        .slice(0, 3);
      for (const g of top3) {
        parentGenreCounts[g.genre] = (parentGenreCounts[g.genre] ?? 0) + 1;
      }
    }
    const parentGenres = Object.entries(parentGenreCounts)
      .sort(([, a], [, b]) => b - a)
      .map(([genre, count]) => ({ genre, count }));

    // Detailed genres: top 5 per song → count how many songs feature each genre
    const detGenreCounts: Record<string, number> = {};
    for (const s of songs) {
      const top5 = [...s.detailed_genres]
        .sort((a, b) => b.probability - a.probability)
        .slice(0, 5);
      for (const g of top5) {
        const label = g.genre.split("---").pop() ?? g.genre;
        detGenreCounts[label] = (detGenreCounts[label] ?? 0) + 1;
      }
    }
    const detailedGenres = Object.entries(detGenreCounts)
      .sort(([, a], [, b]) => b - a)
      .map(([genre, count]) => ({ genre, count }));

    // Instruments: top 10 per song → count occurrences across library
    const instrCounts: Record<string, number> = {};
    for (const s of songs) {
      const top10 = [...s.instruments]
        .sort((a, b) => b.probability - a.probability)
        .slice(0, 10);
      for (const i of top10) {
        instrCounts[i.instrument] = (instrCounts[i.instrument] ?? 0) + 1;
      }
    }
    const allInstruments = (() => {
      const categorized = Object.entries(instrCounts).map(([name, count]) => ({
        name,
        count,
        category: classifyInstrument(name),
      }));
      categorized.sort((a, b) => {
        const catDiff = CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category);
        return catDiff !== 0 ? catDiff : b.count - a.count;
      });
      const catIndexes: Partial<Record<InstrumentCategory, number>> = {};
      return categorized.map((item) => {
        const idx = catIndexes[item.category] ?? 0;
        catIndexes[item.category] = idx + 1;
        const def = INSTRUMENT_CATEGORY_DEFS.find((d) => d.key === item.category)!;
        return { ...item, color: def.palette[idx % def.palette.length] };
      });
    })();

    const avgBpm = bpms.length ? bpms.reduce((a, b) => a + b, 0) / bpms.length : null;
    const avgDur = durations.length ? durations.reduce((a, b) => a + b, 0) / durations.length : null;
    const artistCount = Object.keys(artistCounts).length;

    return {
      totalHours, bpmHist, durHist, danceHist,
      keyData, scaleData, dominantMoodData,
      releaseYears, yearDomain, yearTicks, topArtists,
      parentGenres, detailedGenres, allInstruments,
      avgBpm, avgDur, artistCount,
      songCount: songs.length,
    };
  }, [songs]);

  if (!songs.length) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-600 text-sm">
        No songs in the database yet.
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-6 space-y-8">

      {/* ── Stat Cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard label="Total Songs"    value={String(data.songCount)} />
        <StatCard label="Artists"        value={String(data.artistCount)} />
        <StatCard label="Avg BPM"        value={data.avgBpm?.toFixed(1) ?? "–"} />
        <StatCard label="Avg Duration"   value={data.avgDur ? fmt(data.avgDur) : "–"} />
        <StatCard
          label="Total Music"
          value={`${data.totalHours.toFixed(1)} h`}
          sub={`${(data.totalHours * 60).toFixed(0)} minutes`}
        />
      </div>

      {/* ── Audio Features ── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Audio Features
        </h2>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <ChartCard title="BPM Distribution">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data.bpmHist} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid {...GRID_STYLE} vertical={false} />
                <XAxis dataKey="label" tick={AXIS_STYLE} interval={2} />
                <YAxis tick={AXIS_STYLE} />
                <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} formatter={(v) => [v, "songs"]} />
                <Bar dataKey="count" fill="#818cf8" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Duration Distribution">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data.durHist} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid {...GRID_STYLE} vertical={false} />
                <XAxis
                  dataKey="min"
                  tick={AXIS_STYLE}
                  tickFormatter={(v) => fmt(v as number)}
                  interval={2}
                />
                <YAxis tick={AXIS_STYLE} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM}
                  formatter={(v) => [v, "songs"]}
                  labelFormatter={(l) => `~${fmt(l as number)}`}
                />
                <Bar dataKey="count" fill="#60a5fa" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
          <ChartCard title="Key Distribution">
            <ResponsiveContainer width="100%" height={220}>
              <RadarChart data={data.keyData} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
                <PolarGrid stroke="#1f2937" />
                <PolarAngleAxis dataKey="subject" tick={{ fill: "#9ca3af", fontSize: 11 }} />
                <PolarRadiusAxis tick={false} axisLine={false} />
                <Radar dataKey="value" fill="#818cf8" fillOpacity={0.35} stroke="#818cf8" strokeWidth={1.5} />
                <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} formatter={(v) => [v, "songs"]} />
              </RadarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Major vs Minor">
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={data.scaleData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={75}
                  innerRadius={35}
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  labelLine={{ stroke: "#6b7280" }}
                >
                  {data.scaleData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} formatter={(v) => [v, "songs"]} />
              </PieChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Dominant Mood per Song">
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={data.dominantMoodData}
                  dataKey="count"
                  nameKey="mood"
                  cx="50%"
                  cy="50%"
                  outerRadius={75}
                  innerRadius={32}
                  label={({ mood, percent }) =>
                    percent > 0.04 ? `${mood} ${(percent * 100).toFixed(0)}%` : ""
                  }
                  labelLine={{ stroke: "#6b7280" }}
                >
                  {data.dominantMoodData.map((d, i) => (
                    <Cell key={i} fill={MOOD_COLORS[d.mood] ?? COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM}
                  formatter={(v, name) => [v, name]}
                />
              </PieChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>

        <div className="mt-4">
          <ChartCard title="Danceability Distribution">
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={data.danceHist} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid {...GRID_STYLE} vertical={false} />
                <XAxis
                  dataKey="min"
                  type="number"
                  scale="linear"
                  domain={[0, 1]}
                  ticks={[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]}
                  tick={AXIS_STYLE}
                  padding={{ left: 15, right: 15 }}
                  tickFormatter={(v) => (v as number).toFixed(1)}
                />
                <YAxis tick={AXIS_STYLE} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM}
                  formatter={(v) => [v, "songs"]}
                  labelFormatter={(l) => `~${(l as number).toFixed(2)}`}
                />
                <Bar dataKey="count" fill="#34d399" radius={[2, 2, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      </section>

      {/* ── Timeline ── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Timeline
        </h2>
        <ChartCard title="Songs by Release Year">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.releaseYears} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid {...GRID_STYLE} vertical={false} />
              <XAxis
                dataKey="year"
                type="number"
                scale="linear"
                domain={data.yearDomain ?? ["dataMin", "dataMax"]}
                ticks={data.yearTicks}
                tick={AXIS_STYLE}
                padding={{ left: 15, right: 15 }}
                tickFormatter={(v) => String(v)}
              />
              <YAxis tick={AXIS_STYLE} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM}
                formatter={(v) => [v, "songs"]}
                labelFormatter={(l) => String(l)}
              />
              <Bar dataKey="count" fill="#fbbf24" radius={[2, 2, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </section>

      {/* ── Artists ── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Artists
        </h2>
        <ChartCard title="Top 15 Artists by Song Count">
          <ResponsiveContainer width="100%" height={Math.max(240, data.topArtists.length * 26)}>
            <BarChart
              data={data.topArtists}
              layout="vertical"
              margin={{ top: 0, right: 40, left: 8, bottom: 0 }}
            >
              <CartesianGrid {...GRID_STYLE} horizontal={false} />
              <XAxis type="number" tick={AXIS_STYLE} />
              <YAxis type="category" dataKey="name" tick={{ fill: "#9ca3af", fontSize: 11 }} width={140} />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} formatter={(v) => [v, "songs"]} />
              <Bar dataKey="count" radius={[0, 3, 3, 0]}>
                {data.topArtists.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </section>

      {/* ── Genres ── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Genres
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <ChartCard title="Parent Genres — songs featuring genre (top 3 per song)">
            <ResponsiveContainer width="100%" height={Math.max(200, data.parentGenres.length * 26)}>
              <BarChart
                data={data.parentGenres}
                layout="vertical"
                margin={{ top: 0, right: 50, left: 8, bottom: 0 }}
              >
                <CartesianGrid {...GRID_STYLE} horizontal={false} />
                <XAxis type="number" tick={AXIS_STYLE} />
                <YAxis type="category" dataKey="genre" tick={{ fill: "#9ca3af", fontSize: 11 }} width={100} />
                <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} formatter={(v) => [v, "songs"]} />
                <Bar dataKey="count" radius={[0, 3, 3, 0]}>
                  {data.parentGenres.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Detailed Genres — songs featuring genre (top 5 per song)">
            <ResponsiveContainer width="100%" height={Math.max(200, Math.min(data.detailedGenres.length, 30) * 22)}>
              <BarChart
                data={data.detailedGenres.slice(0, 30)}
                layout="vertical"
                margin={{ top: 0, right: 50, left: 8, bottom: 0 }}
              >
                <CartesianGrid {...GRID_STYLE} horizontal={false} />
                <XAxis type="number" tick={AXIS_STYLE} />
                <YAxis type="category" dataKey="genre" tick={{ fill: "#9ca3af", fontSize: 10 }} width={130} />
                <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} formatter={(v) => [v, "songs"]} />
                <Bar dataKey="count" fill="#a78bfa" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      </section>

      {/* ── Instruments ── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Instruments
        </h2>
        <ChartCard title="Instruments — songs featuring instrument (top 10 per song)">
          <div className="flex flex-wrap gap-3 mb-4 text-xs">
            {INSTRUMENT_CATEGORY_DEFS.map(({ key, label, palette }) => (
              <span key={key} className="flex items-center gap-1 text-gray-500">
                <span className="flex gap-px flex-shrink-0">
                  {palette.slice(0, 3).map((c) => (
                    <span key={c} className="w-2 h-2.5 rounded-sm inline-block" style={{ background: c }} />
                  ))}
                </span>
                {label}
              </span>
            ))}
          </div>
          <ResponsiveContainer width="100%" height={Math.max(300, data.allInstruments.length * 22)}>
            <BarChart
              data={data.allInstruments}
              layout="vertical"
              margin={{ top: 0, right: 50, left: 8, bottom: 0 }}
            >
              <CartesianGrid {...GRID_STYLE} horizontal={false} />
              <XAxis type="number" tick={AXIS_STYLE} />
              <YAxis type="category" dataKey="name" tick={{ fill: "#9ca3af", fontSize: 11 }} width={120} />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} formatter={(v) => [v, "songs"]} />
              <Bar dataKey="count" radius={[0, 3, 3, 0]}>
                {data.allInstruments.map((d) => (
                  <Cell key={d.name} fill={d.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </section>

    </div>
  );
}
