import { useEffect, useMemo, useState } from "react";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
  XAxis, YAxis, CartesianGrid, Tooltip,
  LineChart, Line,
} from "recharts";
import { fetchSongDetail } from "../../services/api";
import { Link, goBack } from "../../router";
import { PlayButton } from "../PlayButton";
import { StatCard } from "../StatCard";
import { Figure, RankedBars } from "../analysis/layout";
import { SongDetails } from "./SongDetails";
import type { Song } from "../../types/song";
import type { SongDetailTimeseries } from "../../types/analysis";
import { COLOR, FONT_MONO, SERIES_EXTENDED as S, gridProps, numericAxis, tooltipProps } from "../../theme";

// Fixed colour per feature (never by selection order). The default selection
// — loudness, arousal, valence, happy — takes the first four validated slots.
const TS_COLORS: Record<string, string> = {
  loudness:           S[0],
  arousal:            S[1],
  valence:            S[2],
  happy:              S[3],
  spectral_centroid:  S[4],
  spectral_rolloff:   S[5],
  spectral_flux:      S[6],
  zero_crossing_rate: S[7],
  dissonance:         S[8],
  approachability:    S[9],
  engagement:         S[10],
  voice:              S[11],
  gender:             S[12],
  sad:                S[13],
  aggressive:         S[7],
  party:              S[4],
  relaxed:            S[5],
  acoustic:           S[6],
  electronic:         S[8],
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

/** Two opposing scores of one ML head, one row each. */
function DualBar({ leftLabel, leftVal, rightLabel, rightVal }: {
  leftLabel: string; leftVal: number; rightLabel: string; rightVal: number;
}) {
  return (
    <RankedBars
      labelWidth={92}
      max={1}
      format={(v) => `${(v * 100).toFixed(0)}%`}
      rows={[
        { label: leftLabel, value: leftVal },
        { label: rightLabel, value: rightVal },
      ]}
    />
  );
}

/** One normalised 0–1 value as a figure over a hairline meter. */
function Meter({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="t-label">{label}</p>
      <p className="text-xl font-medium text-ink leading-none stretch-condensed tabular-nums mt-2">
        {(value * 100).toFixed(1)}%
      </p>
      <div className="mt-2 h-[3px] bg-line">
        <div className="h-full bg-ink-2" style={{ width: `${value * 100}%` }} />
      </div>
    </div>
  );
}

interface Props {
  songs: Song[];
  songId: string;
}

/** One song on its own page (/songs/:id): charts first, the raw field dump last. */
export function SongDetailPage({ songs, songId }: Props) {
  const song = useMemo(() => songs.find((s) => s.id === songId) ?? null, [songs, songId]);

  // Everything but the timeseries is already in the song list; the per-second
  // arrays are large, so they are only fetched for the song being viewed.
  const [timeseries, setTimeseries] = useState<SongDetailTimeseries | null>(null);
  const [tsError,    setTsError]    = useState<string | null>(null);
  const [visibleTs,  setVisibleTs]  = useState<Set<string>>(
    new Set(["loudness", "arousal", "valence", "happy"]),
  );

  const exists = song !== null;
  useEffect(() => {
    if (!exists) return;
    let cancelled = false;
    setTimeseries(null);
    setTsError(null);
    fetchSongDetail(songId)
      .then((d) => { if (!cancelled) setTimeseries(d.timeseries); })
      .catch((e: Error) => { if (!cancelled) setTsError(e.message); });
    return () => { cancelled = true; };
  }, [songId, exists]);

  // Build timeseries chart data.
  // DSP/EffNet features are 1 sample/second; MusiCNN (arousal, valence) are 1 sample/~3s.
  // Scale MusiCNN indices so both span the full song duration on the x-axis.
  const tsChartData = useMemo(() => {
    if (!timeseries) return [];
    const ts = timeseries;
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
  }, [timeseries, visibleTs]);

  const toggleTs = (key: string) => {
    setVisibleTs((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  if (!song) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 font-mono text-xs text-ink-3">
        <p>Song not found.</p>
        <Link to="/songs" className="btn-quiet">Back to all songs</Link>
      </div>
    );
  }

  const profile = song.ml_profile;
  const dsp     = song.dsp_features;
  const file    = song.file_metadata;
  const track   = song.track_metadata;

  // Mood data for radar
  const moodRadarData = song.ml_moods
    ? Object.entries(song.ml_moods).map(([key, val]) => ({
        subject: key,
        value: val ?? 0,
      }))
    : [];

  // Instruments data
  const instrData = [...song.instruments]
    .sort((a, b) => b.probability - a.probability)
    .slice(0, 12);

  // Parent genres data
  const genreData = [...song.parent_genres].sort((a, b) => b.percentage - a.percentage);

  // All TS keys available
  const allTsKeys = timeseries
    ? (Object.keys(timeseries) as (keyof SongDetailTimeseries)[]).filter((k) => {
        const arr = timeseries[k];
        return Array.isArray(arr) && arr.length > 0;
      })
    : [];

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-7xl mx-auto px-4 pt-3 pb-16 md:px-6 md:pt-4 space-y-10">

        {/* Header — the song is the subject of the page */}
        <div>
          <button
            onClick={() => goBack("/songs")}
            className="btn-quiet inline-flex items-center gap-1.5 h-8"
          >
            <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path d="M10.5 6h-9M5.5 2l-4 4 4 4" />
            </svg>
            Back
          </button>
          <div className="flex items-start gap-3 mt-3">
            <PlayButton songId={song.id} className="mt-1 !w-9 !h-9 border border-line-strong" />
            <div className="min-w-0">
              <h2 className="text-3xl font-semibold text-ink stretch-semi tracking-[-0.02em] leading-[1.05] break-words">
                {song.title ?? "Unknown"}
              </h2>
              <p className="text-lg text-ink-2 mt-2 truncate">
                {song.artist ?? "Unknown artist"}
                {track?.featured_artists && track.featured_artists.length > 0 && (
                  <span className="text-ink-3"> feat. {track.featured_artists.join(", ")}</span>
                )}
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 border-y border-line-strong mt-6 max-w-3xl">
            {file?.duration_seconds != null && (
              <StatCard label="Duration" value={fmt(file.duration_seconds)} />
            )}
            {track?.release_date && (
              <StatCard label="Released" value={track.release_date.slice(0, 4)} />
            )}
            {track?.playcount != null && (
              <StatCard label="Last.fm Plays" value={track.playcount.toLocaleString()} />
            )}
            {dsp?.danceability != null && (
              <StatCard label="Danceability" value={`${(dsp.danceability * 100).toFixed(0)}%`} />
            )}
          </div>
        </div>

        {/* Mood + Profile */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-12 gap-y-10 border-t border-line-strong pt-5">

          <Figure title="Mood Profile">
            {moodRadarData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <RadarChart data={moodRadarData} margin={{ top: 30, right: 55, bottom: 30, left: 55 }}>
                  <PolarGrid stroke={COLOR.line} />
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
                            fill={COLOR.ink2}
                            fontSize={11}
                            fontWeight={500}
                          >
                            {payload.value}
                          </text>
                          <text
                            x={nx}
                            y={ny + 14}
                            textAnchor="middle"
                            fill={COLOR.ink3}
                            fontSize={10}
                            fontFamily={FONT_MONO}
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
                    fill={COLOR.signal}
                    fillOpacity={0.16}
                    stroke={COLOR.signal}
                    strokeWidth={1.5}
                    activeDot={false}
                  />
                </RadarChart>
              </ResponsiveContainer>
            ) : (
              <p className="font-mono text-2xs text-ink-3">No mood data</p>
            )}
          </Figure>

          <Figure title="ML Profile Scores">
            {profile ? (
              <div className="space-y-4">
                <DualBar
                  leftLabel="Niche"
                  leftVal={profile.niche_score ?? 0}
                  rightLabel="Mainstream"
                  rightVal={profile.mainstream_score ?? 0}
                />
                <DualBar
                  leftLabel="Background"
                  leftVal={profile.background_score ?? 0}
                  rightLabel="Active"
                  rightVal={profile.active_score ?? 0}
                />
                <DualBar
                  leftLabel="Instrumental"
                  leftVal={profile.instrumental_score ?? 0}
                  rightLabel="Vocal"
                  rightVal={profile.vocal_score ?? 0}
                />
                <DualBar
                  leftLabel="Female"
                  leftVal={profile.female_score ?? 0}
                  rightLabel="Male"
                  rightVal={profile.male_score ?? 0}
                />
                <div className="grid grid-cols-2 gap-8 pt-4 border-t border-line">
                  <Meter label="Arousal" value={normalizeAV(profile.arousal ?? 1)} />
                  <Meter label="Valence" value={normalizeAV(profile.valence ?? 1)} />
                </div>
              </div>
            ) : (
              <p className="font-mono text-2xs text-ink-3">No ML profile data</p>
            )}
          </Figure>
        </div>

        {/* Genres + Instruments */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-12 gap-y-10 border-t border-line-strong pt-5">

          <Figure title="Genre Distribution" note="share">
            {genreData.length > 0 ? (
              <RankedBars
                labelWidth={120}
                rows={genreData.map((g) => ({ label: g.genre, value: g.percentage }))}
                format={(v) => `${(v * 100).toFixed(0)}%`}
              />
            ) : (
              <p className="font-mono text-2xs text-ink-3">No genre data</p>
            )}
          </Figure>

          <Figure title="Top Instruments" note="probability">
            {instrData.length > 0 ? (
              <RankedBars
                labelWidth={120}
                max={1}
                rows={instrData.map((i) => ({ label: i.instrument, value: i.probability }))}
                format={(v) => v.toFixed(2)}
              />
            ) : (
              <p className="font-mono text-2xs text-ink-3">No instrument data</p>
            )}
          </Figure>
        </div>

        {/* Audio details */}
        {dsp && (
          <div className="border-t border-line-strong pt-5">
            <Figure title="Audio Details">
              <dl className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 border-t border-line">
                {[
                  { label: "BPM",             val: dsp.bpm?.toFixed(1) },
                  { label: "Beat Confidence", val: dsp.beat_confidence ? `${(dsp.beat_confidence * 100).toFixed(0)}%` : null },
                  { label: "Key",             val: dsp.key ? `${dsp.key} ${dsp.scale}` : null },
                  { label: "Key Strength",    val: dsp.key_strength?.toFixed(3) },
                  { label: "Tuning Hz",       val: dsp.tuning_frequency_hz?.toFixed(1) },
                  { label: "LUFS",            val: dsp.integrated_lufs?.toFixed(1) },
                  { label: "Loudness dB",     val: dsp.loudness_db?.toFixed(1) },
                  { label: "Dyn. Complexity", val: dsp.dynamic_complexity?.toFixed(3) },
                  { label: "Dissonance",      val: dsp.dissonance?.toFixed(3) },
                  { label: "Spec. Centroid",  val: dsp.spectral_centroid_mean?.toFixed(0) },
                  { label: "Chord Change",    val: dsp.chord_change_rate?.toFixed(3) },
                  { label: "Top Chord",       val: dsp.most_common_chord },
                ].map(({ label, val }) => (
                  val != null ? (
                    <div key={label} className="py-2.5 pr-4 border-b border-line min-w-0">
                      <dt className="t-label">{label}</dt>
                      <dd className="font-mono text-sm text-ink mt-1 truncate">{val}</dd>
                    </div>
                  ) : null
                ))}
              </dl>
            </Figure>
          </div>
        )}

        {/* Timeseries — the only part loaded on demand */}
        <div className="border-t border-line-strong pt-5">
          <Figure title="Feature Timeseries" note="each series min-max normalised">
            {tsError ? (
              <div className="border-l-2 border-bad bg-bad/5 px-4 py-3 text-sm text-bad">
                {tsError}
              </div>
            ) : !timeseries ? (
              <div className="flex items-center justify-center h-48 font-mono text-xs text-ink-3">
                Loading…
              </div>
            ) : (
              <>
                {/* Toggle buttons */}
                <div className="flex flex-wrap gap-x-1 gap-y-0.5 mb-5">
                  {allTsKeys.map((k) => {
                    const on = visibleTs.has(k);
                    const color = TS_COLORS[k] ?? COLOR.data;
                    return (
                      <button
                        key={k}
                        onClick={() => toggleTs(k)}
                        aria-pressed={on}
                        className={`flex items-center gap-1.5 px-2 h-6 rounded-sm text-xs ${
                          on ? "text-ink bg-raised" : "text-ink-3 hover:text-ink"
                        }`}
                      >
                        <span
                          className="w-2 h-2 shrink-0"
                          style={{ background: on ? color : "transparent", boxShadow: `inset 0 0 0 1px ${color}` }}
                        />
                        {TS_LABEL[k] ?? k}
                      </button>
                    );
                  })}
                </div>

                {tsChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={tsChartData} margin={{ top: 4, right: 16, left: -16, bottom: 8 }}>
                      <CartesianGrid {...gridProps} vertical={false} />
                      <XAxis
                        dataKey="sec"
                        {...numericAxis}
                        label={{ value: "seconds", position: "insideBottom", offset: -4, fill: COLOR.ink3, fontSize: 10, fontFamily: FONT_MONO }}
                      />
                      <YAxis {...numericAxis} axisLine={false} domain={[0, 1]} />
                      <Tooltip
                        {...tooltipProps}
                        cursor={{ stroke: COLOR.lineStrong }}
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
                          stroke={TS_COLORS[k] ?? COLOR.data}
                          strokeWidth={1.5}
                          dot={false}
                          connectNulls
                          isAnimationActive={false}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex items-center justify-center h-48 font-mono text-xs text-ink-3">
                    Select at least one feature above
                  </div>
                )}
              </>
            )}
          </Figure>
        </div>

        {/* Raw values — every stored field, as in the database */}
        <div className="border-t border-line-strong pt-5">
          <Figure title="All Stored Fields" note="raw database values">
            <SongDetails song={song} />
          </Figure>
        </div>

      </div>
    </div>
  );
}
