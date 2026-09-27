import { useMemo } from "react";
import { StatCard } from "../StatCard";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from "recharts";
import type { Song } from "../../types/song";
import {
  COLOR, FONT_MONO, SERIES_EXTENDED,
  numericAxis, gridProps, tooltipProps,
} from "../../theme";
import { Figure, RankedBars, Section } from "./layout";

type InstrumentCategory =
  | "percussion" | "bass" | "guitar" | "piano"
  | "strings" | "brass" | "woodwind" | "voice" | "synth" | "other";

// One hue per family, in the validated categorical order; "other" stays neutral.
const INSTRUMENT_CATEGORY_DEFS: Array<{ key: InstrumentCategory; label: string; keywords: string[]; color: string }> = [
  { key: "percussion", label: "Percussion / Drums",   keywords: ["drum","percussion","cymbal","hi-hat","snare","kick","tom","clap"],                     color: SERIES_EXTENDED[0] },
  { key: "bass",       label: "Bass",                 keywords: ["bass"],                                                                                color: SERIES_EXTENDED[1] },
  { key: "guitar",     label: "Guitar family",        keywords: ["guitar","banjo","ukulele","mandolin","sitar","lute"],                                   color: SERIES_EXTENDED[2] },
  { key: "piano",      label: "Piano / Keys",         keywords: ["piano","keyboard","organ","harpsichord","accordion","celesta"],                         color: SERIES_EXTENDED[3] },
  { key: "strings",    label: "Orchestral strings",   keywords: ["violin","cello","viola","string","harp","fiddle","contrabass"],                         color: SERIES_EXTENDED[4] },
  { key: "brass",      label: "Brass",                keywords: ["trumpet","trombone","tuba","horn","brass","cornet","flugelhorn"],                       color: SERIES_EXTENDED[5] },
  { key: "woodwind",   label: "Woodwind",             keywords: ["saxophone","flute","clarinet","oboe","bassoon","wind","piccolo"],                       color: SERIES_EXTENDED[6] },
  { key: "voice",      label: "Voice / Vocals",       keywords: ["voice","vocal","choir","singing","chant"],                                              color: SERIES_EXTENDED[7] },
  { key: "synth",      label: "Electronic / Synth",   keywords: ["synth","electronic","sampler","theremin"],                                              color: SERIES_EXTENDED[8] },
  { key: "other",      label: "Other",                keywords: [],                                                                                      color: COLOR.ink4 },
];

const CATEGORY_ORDER = INSTRUMENT_CATEGORY_DEFS.map((c) => c.key);

function classifyInstrument(name: string): InstrumentCategory {
  const n = name.toLowerCase();
  for (const def of INSTRUMENT_CATEGORY_DEFS) {
    if (def.keywords.some((k) => n.includes(k))) return def.key;
  }
  return "other";
}

const BAR_RADIUS: [number, number, number, number] = [1, 1, 0, 0];

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

/** Two-part share as one split bar with the numbers set underneath. */
function SplitBar({ data }: { data: { name: string; value: number }[] }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const sorted = [...data].sort((a, b) => b.value - a.value);
  return (
    <div>
      <div className="flex h-7 gap-[2px]">
        {sorted.map((d) => (
          <div
            key={d.name}
            title={`${d.name}: ${d.value} songs`}
            style={{
              width: `${(d.value / total) * 100}%`,
              background: d.name === "minor" ? COLOR.ink4 : COLOR.data,
            }}
          />
        ))}
      </div>
      <div className="flex mt-2.5">
        {sorted.map((d) => (
          <div key={d.name} className="min-w-0 pr-3 whitespace-nowrap" style={{ width: `${(d.value / total) * 100}%` }}>
            <p className="text-xl font-medium text-ink leading-none stretch-condensed tabular-nums">
              {((d.value / total) * 100).toFixed(0)}%
            </p>
            <p className="t-label mt-1">{d.name} · {d.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
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
      return categorized.map((item) => {
        const def = INSTRUMENT_CATEGORY_DEFS.find((d) => d.key === item.category)!;
        return { ...item, color: def.color };
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
      <div className="flex items-center justify-center h-64 font-mono text-xs text-ink-3">
        No songs in the database yet.
      </div>
    );
  }


  return (
    <div className="max-w-7xl mx-auto px-6 pt-6 pb-16 space-y-10">

      {/* ── Figures ── */}
      <div className="grid grid-cols-2 sm:grid-cols-5 border-y border-line-strong">
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
      <Section title="Audio Features">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-10 gap-y-10">
          <Figure title="BPM Distribution">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data.bpmHist} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid {...gridProps} vertical={false} />
                <XAxis dataKey="label" {...numericAxis} interval={2} />
                <YAxis {...numericAxis} axisLine={false} />
                <Tooltip {...tooltipProps} formatter={(v) => [v, "songs"]} />
                <Bar dataKey="count" fill={COLOR.data} radius={BAR_RADIUS} />
              </BarChart>
            </ResponsiveContainer>
          </Figure>

          <Figure title="Duration Distribution">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data.durHist} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid {...gridProps} vertical={false} />
                <XAxis
                  dataKey="min"
                  {...numericAxis}
                  tickFormatter={(v) => fmt(v as number)}
                  interval={2}
                />
                <YAxis {...numericAxis} axisLine={false} />
                <Tooltip
                  {...tooltipProps}
                  formatter={(v) => [v, "songs"]}
                  labelFormatter={(l) => `~${fmt(l as number)}`}
                />
                <Bar dataKey="count" fill={COLOR.data} radius={BAR_RADIUS} />
              </BarChart>
            </ResponsiveContainer>
          </Figure>

          <Figure title="Key Distribution">
            <ResponsiveContainer width="100%" height={240}>
              <RadarChart data={data.keyData} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
                <PolarGrid stroke={COLOR.line} />
                <PolarAngleAxis dataKey="subject" tick={{ fill: COLOR.ink2, fontSize: 11, fontFamily: FONT_MONO }} />
                <PolarRadiusAxis tick={false} axisLine={false} />
                <Radar dataKey="value" fill={COLOR.data} fillOpacity={0.18} stroke={COLOR.data} strokeWidth={1.5} />
                <Tooltip {...tooltipProps} formatter={(v) => [v, "songs"]} />
              </RadarChart>
            </ResponsiveContainer>
          </Figure>

          <div className="space-y-10">
            <Figure title="Major vs Minor">
              <SplitBar data={data.scaleData} />
            </Figure>

            <Figure title="Dominant Mood per Song" note="songs · share">
              <RankedBars
                labelWidth={88}
                valueWidth={72}
                rows={data.dominantMoodData.map((d) => ({ label: d.mood, value: d.count }))}
                format={(v) => {
                  const total = data.dominantMoodData.reduce((s, d) => s + d.count, 0) || 1;
                  return `${v} · ${Math.round((v / total) * 100)}%`;
                }}
              />
            </Figure>
          </div>

          <Figure title="Danceability Distribution" className="lg:col-span-2">
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={data.danceHist} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid {...gridProps} vertical={false} />
                <XAxis
                  dataKey="min"
                  type="number"
                  scale="linear"
                  domain={[0, 1]}
                  ticks={[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]}
                  {...numericAxis}
                  padding={{ left: 15, right: 15 }}
                  tickFormatter={(v) => (v as number).toFixed(1)}
                />
                <YAxis {...numericAxis} axisLine={false} />
                <Tooltip
                  {...tooltipProps}
                  formatter={(v) => [v, "songs"]}
                  labelFormatter={(l) => `~${(l as number).toFixed(2)}`}
                />
                <Bar dataKey="count" fill={COLOR.data} radius={BAR_RADIUS} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          </Figure>
        </div>
      </Section>

      {/* ── Timeline ── */}
      <Section title="Timeline">
        <Figure title="Songs by Release Year">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.releaseYears} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid {...gridProps} vertical={false} />
              <XAxis
                dataKey="year"
                type="number"
                scale="linear"
                domain={data.yearDomain ?? ["dataMin", "dataMax"]}
                ticks={data.yearTicks}
                {...numericAxis}
                padding={{ left: 15, right: 15 }}
                tickFormatter={(v) => String(v)}
              />
              <YAxis {...numericAxis} axisLine={false} />
              <Tooltip
                {...tooltipProps}
                  formatter={(v) => [v, "songs"]}
                labelFormatter={(l) => String(l)}
              />
              <Bar dataKey="count" fill={COLOR.data} radius={BAR_RADIUS} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </Figure>
      </Section>

      {/* ── Artists ── */}
      <Section title="Artists">
        <Figure title="Top 15 Artists by Song Count" note="songs">
          <RankedBars
            className="max-w-3xl"
            labelWidth={180}
            rows={data.topArtists.map((a) => ({ label: a.name, value: a.count }))}
          />
        </Figure>
      </Section>

      {/* ── Genres ── */}
      <Section title="Genres">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-10 gap-y-10">
          <Figure title="Parent Genres" note="songs featuring genre (top 3 per song)">
            <RankedBars
              labelWidth={120}
              rows={data.parentGenres.map((g) => ({ label: g.genre, value: g.count }))}
            />
          </Figure>

          <Figure title="Detailed Genres" note="songs featuring genre (top 5 per song)">
            <RankedBars
              labelWidth={140}
              rows={data.detailedGenres.slice(0, 30).map((g) => ({ label: g.genre, value: g.count }))}
            />
          </Figure>
        </div>
      </Section>

      {/* ── Instruments ── */}
      <Section title="Instruments">
        <Figure title="Instruments" note="songs featuring instrument (top 10 per song)">
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 mb-4">
            {INSTRUMENT_CATEGORY_DEFS.map(({ key, label, color }) => (
              <span key={key} className="flex items-center gap-1.5 text-xs text-ink-3">
                <span className="w-2 h-2 flex-shrink-0" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>
          <RankedBars
            className="xl:columns-2 gap-x-10"
            labelWidth={132}
            max={Math.max(1, ...data.allInstruments.map((d) => d.count))}
            rows={data.allInstruments.map((d) => ({ label: d.name, value: d.count, color: d.color }))}
          />
        </Figure>
      </Section>

    </div>
  );
}
