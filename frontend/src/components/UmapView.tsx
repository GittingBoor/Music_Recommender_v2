import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useRef } from "react";
import type { Song } from "../types/song";
import type { UmapResponse } from "../types/umap";
import { fetchUmap } from "../services/api";
import { UmapCanvas2D } from "./UmapCanvas2D";

const API_BASE = "http://localhost:8000";

// ─── Feature definitions ──────────────────────────────────────────────────────

const FEATURE_OPTIONS = [
  { value: "bpm",                    label: "BPM",               group: "Rhythm"   },
  { value: "danceability",           label: "Danceability",      group: "Rhythm"   },
  { value: "beat_confidence",        label: "Beat Confidence",   group: "Rhythm"   },
  { value: "onset_rate",             label: "Onset Rate",        group: "Rhythm"   },
  { value: "key_strength",           label: "Key Strength",      group: "Tonal"    },
  { value: "chord_strength_mean",    label: "Chord Strength",    group: "Tonal"    },
  { value: "chord_change_rate",      label: "Chord Change Rate", group: "Tonal"    },
  { value: "integrated_lufs",        label: "Loudness (LUFS)",   group: "Loudness" },
  { value: "loudness_range_lu",      label: "Loudness Range",    group: "Loudness" },
  { value: "dynamic_complexity",     label: "Dyn. Complexity",   group: "Loudness" },
  { value: "loudness_db",            label: "Loudness (dB)",     group: "Loudness" },
  { value: "spectral_centroid_mean", label: "Spectral Centroid", group: "Spectral" },
  { value: "spectral_rolloff_mean",  label: "Spectral Rolloff",  group: "Spectral" },
  { value: "spectral_flux_mean",     label: "Spectral Flux",     group: "Spectral" },
  { value: "zero_crossing_rate",     label: "Zero Crossing",     group: "Spectral" },
  { value: "dissonance",             label: "Dissonance",        group: "Spectral" },
  { value: "happy",                  label: "Happy",             group: "Mood"     },
  { value: "sad",                    label: "Sad",               group: "Mood"     },
  { value: "aggressive",             label: "Aggressive",        group: "Mood"     },
  { value: "party",                  label: "Party",             group: "Mood"     },
  { value: "relaxed",                label: "Relaxed",           group: "Mood"     },
  { value: "acoustic",               label: "Acoustic",          group: "Mood"     },
  { value: "electronic",             label: "Electronic",        group: "Mood"     },
  { value: "arousal",                label: "Arousal",           group: "Profile"  },
  { value: "valence",                label: "Valence",           group: "Profile"  },
  { value: "mainstream_score",        label: "Approachability",   group: "Profile"  },
  { value: "active_score",           label: "Engagement",        group: "Profile"  },
  { value: "vocal_score",            label: "Voice",             group: "Profile"  },
] as const;

type FeatureValue = (typeof FEATURE_OPTIONS)[number]["value"];
type FeatureMode  = "all" | "custom";

const ALL_FEATURE_VALUES: string[] = FEATURE_OPTIONS.map((o) => o.value);
const FEATURE_LABEL: Record<string, string> = Object.fromEntries(
  FEATURE_OPTIONS.map((o) => [o.value, o.label])
);
const FEATURE_GROUPS = [...new Set(FEATURE_OPTIONS.map((o) => o.group))];

const GENRE_PALETTE = [
  "#6366f1", "#ef4444", "#ec4899", "#f59e0b", "#10b981",
  "#06b6d4", "#8b5cf6", "#84cc16", "#22c55e", "#3b82f6",
  "#f97316", "#14b8a6", "#a855f7", "#6b7280",
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(v: number | null | undefined, decimals = 2): string {
  return v == null ? "—" : v.toFixed(decimals);
}

function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// Essentia MusiCNN outputs arousal/valence on a 1–9 scale, not 0–1.
function normalizeAV(v: number | null | undefined): number {
  if (v == null) return 0;
  if (v <= 1) return Math.max(0, Math.min(1, v));
  return Math.max(0, Math.min(1, (v - 1) / 8));
}

function Bar({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="flex items-center gap-1.5 min-w-0 mt-0.5">
      <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-gray-400 text-[10px] w-7 text-right flex-shrink-0">{pct}%</span>
    </div>
  );
}

// ─── Tooltip ──────────────────────────────────────────────────────────────────

interface TooltipState { text: string; x: number; y: number }
type SetTip = (t: TooltipState | null) => void;

function Tip({ text, children, set }: { text: string; children: React.ReactNode; set: SetTip }) {
  return (
    <span
      className="cursor-help"
      onMouseEnter={(e) => {
        const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
        set({ text, x: r.left + r.width / 2, y: r.top - 6 });
      }}
      onMouseLeave={() => set(null)}
    >
      {children}
    </span>
  );
}

function TooltipPortal({ tip }: { tip: TooltipState | null }) {
  if (!tip) return null;
  return createPortal(
    <div
      className="fixed z-50 px-2 py-1.5 rounded text-[11px] text-gray-200 bg-gray-800 border border-gray-700 shadow-xl leading-snug pointer-events-none max-w-[220px]"
      style={{ left: tip.x, top: tip.y, transform: "translate(-50%, -100%)" }}
    >
      {tip.text}
    </div>,
    document.body
  );
}

// ─── Axis selector ────────────────────────────────────────────────────────────

function AxisSelect({ label, value, onChange }: {
  label: string;
  value: FeatureValue;
  onChange: (v: FeatureValue) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
        {label} axis
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as FeatureValue)}
        className="w-full bg-gray-900 border border-gray-700 text-gray-200 text-xs rounded px-2 py-1.5 focus:outline-none focus:border-indigo-500"
      >
        {FEATURE_GROUPS.map((group) => (
          <optgroup key={group} label={group}>
            {FEATURE_OPTIONS.filter((o) => o.group === group).map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
}

// ─── Tooltip texts ────────────────────────────────────────────────────────────

const TIPS: Record<string, string> = {
  bpm:             "Beats per minute — higher = faster, more energetic tempo",
  key:             "Musical key and scale (major/minor) detected in the track",
  duration:        "Total length of the track",
  danceability:    "How suitable for dancing based on rhythm regularity and beat strength. High = very danceable",
  arousal:         "Perceived energy level. High = exciting and intense, Low = calm and ambient",
  valence:         "Emotional tone. High = happy and uplifting, Low = sad or melancholic",
  approachability: "How mainstream vs. niche the track sounds. High = broad audience appeal",
  engagement:      "Active listening vs. background music. High = demands attention",
  voice:           "Vocal presence. High = strongly vocal, Low = mostly instrumental",
  gender:          "Detected gender of the primary vocalist and confidence score",
  happy:           "Probability the track sounds happy and cheerful",
  sad:             "Probability the track sounds sad or somber",
  aggressive:      "Probability the track sounds aggressive or intense",
  party:           "Probability the track fits a party or upbeat social context",
  relaxed:         "Probability the track sounds calm and laid-back",
  acoustic:        "Probability the track uses primarily acoustic instrumentation",
  electronic:      "Probability the track uses primarily electronic sounds",
  parent_genre:    "Top-level genre category from the Discogs 400-genre ML classifier. Dot color on the map corresponds to this",
  detailed_genre:  "Fine-grained genre from 400 Discogs categories",
  mb_tags:         "Genre tags contributed by the MusicBrainz community database",
};

// ─── Song info panel ──────────────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">
      {children}
    </p>
  );
}

const MOODS: [string, keyof NonNullable<Song["ml_moods"]>][] = [
  ["Happy",      "happy"],
  ["Party",      "party"],
  ["Electronic", "electronic"],
  ["Acoustic",   "acoustic"],
  ["Relaxed",    "relaxed"],
  ["Aggressive", "aggressive"],
  ["Sad",        "sad"],
];

function SongInfoPanel({ song }: { song: Song }) {
  const dsp     = song.dsp_features;
  const profile = song.ml_profile;
  const moods   = song.ml_moods;
  const lastfm  = song.track_metadata;

  const topGenres         = [...song.parent_genres].sort((a, b) => b.percentage - a.percentage).slice(0, 5);
  const topDetailedGenres = [...song.detailed_genres].sort((a, b) => b.probability - a.probability).slice(0, 4);
  const mbGenres          = lastfm?.mb_genres ?? [];
  const featuredArtists   = lastfm?.featured_artists ?? [];

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [tip,     setTip]     = useState<TooltipState | null>(null);

  const togglePlay = () => {
    const el = audioRef.current;
    if (!el) return;
    if (playing) { el.pause(); setPlaying(false); }
    else el.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  };

  useEffect(() => {
    const el = audioRef.current;
    if (el) { el.pause(); el.currentTime = 0; }
    setPlaying(false);
  }, [song.id]);

  const danceabilityPct = dsp?.danceability != null
    ? `${Math.round(dsp.danceability * 100)}%`
    : "—";

  const keyDisplay = dsp?.key && dsp?.scale ? `${dsp.key} ${dsp.scale}` : "—";

  return (
    <>
      <TooltipPortal tip={tip} />
      <div className="flex flex-col gap-3 text-sm pb-2">

        {/* Title / Artist */}
        <div>
          <p className="font-bold text-white text-base leading-tight">{song.title ?? "Unknown"}</p>
          <p className="text-indigo-400 text-sm mt-0.5 truncate">{song.artist ?? "Unknown Artist"}</p>
          {featuredArtists.length > 0 && (
            <p className="text-gray-500 text-xs mt-0.5">feat. {featuredArtists.join(", ")}</p>
          )}
        </div>

        <div className="border-t border-gray-800" />

        {/* Audio preview */}
        <div className="flex items-center gap-2">
          {song.has_preview && (
            <audio
              ref={audioRef}
              src={`${API_BASE}/api/audio/${song.id}`}
              onEnded={() => setPlaying(false)}
            />
          )}
          <div className="relative group">
            <button
              onClick={song.has_preview ? togglePlay : undefined}
              disabled={!song.has_preview}
              className={`flex items-center justify-center w-8 h-8 rounded-full border transition-colors
                ${song.has_preview
                  ? "border-indigo-500 text-indigo-400 hover:bg-indigo-500/20 cursor-pointer"
                  : "border-gray-700 text-gray-700 cursor-not-allowed"}`}
            >
              {playing ? (
                <svg viewBox="0 0 16 16" className="w-4 h-4" fill="currentColor">
                  <rect x="3" y="2" width="4" height="12" rx="1" />
                  <rect x="9" y="2" width="4" height="12" rx="1" />
                </svg>
              ) : (
                <svg viewBox="0 0 16 16" className="w-4 h-4" fill="currentColor">
                  <path d="M4 2.5l10 5.5-10 5.5V2.5z" />
                </svg>
              )}
            </button>
            {!song.has_preview && (
              <div className="pointer-events-none absolute left-10 top-1/2 -translate-y-1/2 hidden group-hover:flex z-20 whitespace-nowrap px-2 py-1 rounded text-xs text-gray-300 bg-gray-800 border border-gray-700 shadow-lg">
                Kein Sample verfügbar
              </div>
            )}
          </div>
          <span className="text-[11px] text-gray-500">
            {song.has_preview ? "15s preview" : "No preview"}
          </span>
        </div>

        <div className="border-t border-gray-800" />

        {/* Audio — fixed 4 rows, single column */}
        <div>
          <SectionTitle>Audio</SectionTitle>
          <div className="space-y-1.5 text-xs">
            {(
              [
                ["BPM",         fmt(dsp?.bpm, 1),  "bpm"],
                ["Key",         keyDisplay,         "key"],
                ["Duration",    fmtDuration(song.file_metadata?.duration_seconds), "duration"],
                ["Danceability", danceabilityPct,   "danceability"],
              ] as [string, string, string][]
            ).map(([label, value, tipKey]) => (
              <div key={label} className="flex justify-between items-center">
                <Tip text={TIPS[tipKey]} set={setTip}>
                  <span className="text-gray-500">{label}</span>
                </Tip>
                <span className="text-gray-200 font-mono">{value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-gray-800" />

        {/* Moods — all 7, bar or dash */}
        <div>
          <SectionTitle>Moods</SectionTitle>
          <div className="space-y-2">
            {MOODS.map(([label, key]) => {
              const val = moods?.[key];
              return (
                <div key={key}>
                  <Tip text={TIPS[key as string]} set={setTip}>
                    <span className="text-gray-500 text-xs">{label}</span>
                  </Tip>
                  {val != null ? <Bar value={val} /> : (
                    <div className="mt-0.5 text-gray-700 text-[10px]">—</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="border-t border-gray-800" />

        {/* Profile — arousal + valence + all profile fields */}
        <div>
          <SectionTitle>Profile</SectionTitle>
          <div className="space-y-2">
            {/* Arousal */}
            <div>
              <Tip text={TIPS.arousal} set={setTip}>
                <span className="text-gray-500 text-xs">Arousal</span>
              </Tip>
              {profile ? <Bar value={normalizeAV(profile.arousal)} /> : (
                <div className="mt-0.5 text-gray-700 text-[10px]">—</div>
              )}
            </div>
            {/* Valence */}
            <div>
              <Tip text={TIPS.valence} set={setTip}>
                <span className="text-gray-500 text-xs">Valence</span>
              </Tip>
              {profile ? <Bar value={normalizeAV(profile.valence)} /> : (
                <div className="mt-0.5 text-gray-700 text-[10px]">—</div>
              )}
            </div>
            {/* Approachability */}
            <div>
              <div className="text-xs text-gray-500 mb-0.5">
                <Tip text={TIPS.approachability} set={setTip}><span>Approachability</span></Tip>
              </div>
              <div className="flex justify-between text-xs text-gray-400 mb-0.5"><span>niche</span><span>{profile?.niche_score != null ? (profile.niche_score * 100).toFixed(0) + "%" : "—"}</span></div>
              {profile ? <Bar value={profile.niche_score ?? 0} /> : null}
              <div className="flex justify-between text-xs text-gray-400 mt-1 mb-0.5"><span>mainstream</span><span>{profile?.mainstream_score != null ? (profile.mainstream_score * 100).toFixed(0) + "%" : "—"}</span></div>
              {profile ? <Bar value={profile.mainstream_score ?? 0} /> : null}
            </div>
            {/* Engagement */}
            <div>
              <div className="text-xs text-gray-500 mb-0.5">
                <Tip text={TIPS.engagement} set={setTip}><span>Engagement</span></Tip>
              </div>
              <div className="flex justify-between text-xs text-gray-400 mb-0.5"><span>background</span><span>{profile?.background_score != null ? (profile.background_score * 100).toFixed(0) + "%" : "—"}</span></div>
              {profile ? <Bar value={profile.background_score ?? 0} /> : null}
              <div className="flex justify-between text-xs text-gray-400 mt-1 mb-0.5"><span>active</span><span>{profile?.active_score != null ? (profile.active_score * 100).toFixed(0) + "%" : "—"}</span></div>
              {profile ? <Bar value={profile.active_score ?? 0} /> : null}
            </div>
            {/* Voice */}
            <div>
              <div className="text-xs text-gray-500 mb-0.5">
                <Tip text={TIPS.voice} set={setTip}><span>Voice</span></Tip>
              </div>
              <div className="flex justify-between text-xs text-gray-400 mb-0.5"><span>instrumental</span><span>{profile?.instrumental_score != null ? (profile.instrumental_score * 100).toFixed(0) + "%" : "—"}</span></div>
              {profile ? <Bar value={profile.instrumental_score ?? 0} /> : null}
              <div className="flex justify-between text-xs text-gray-400 mt-1 mb-0.5"><span>vocal</span><span>{profile?.vocal_score != null ? (profile.vocal_score * 100).toFixed(0) + "%" : "—"}</span></div>
              {profile ? <Bar value={profile.vocal_score ?? 0} /> : null}
            </div>
            {/* Gender */}
            <div>
              <div className="text-xs text-gray-500 mb-0.5">
                <Tip text={TIPS.gender} set={setTip}><span>Gender</span></Tip>
              </div>
              <div className="flex justify-between text-xs text-gray-400 mb-0.5"><span>female</span><span>{profile?.female_score != null ? (profile.female_score * 100).toFixed(0) + "%" : "—"}</span></div>
              {profile ? <Bar value={profile.female_score ?? 0} /> : null}
              <div className="flex justify-between text-xs text-gray-400 mt-1 mb-0.5"><span>male</span><span>{profile?.male_score != null ? (profile.male_score * 100).toFixed(0) + "%" : "—"}</span></div>
              {profile ? <Bar value={profile.male_score ?? 0} /> : null}
            </div>
          </div>
        </div>

        {/* Genres */}
        {(topGenres.length > 0 || topDetailedGenres.length > 0 || mbGenres.length > 0) && (
          <div className="border-t border-gray-800" />
        )}

        {topGenres.length > 0 && (
          <div>
            <Tip text={TIPS.parent_genre} set={setTip}>
              <SectionTitle>Genre (parent)</SectionTitle>
            </Tip>
            <div className="space-y-1">
              {topGenres.map((g) => (
                <div key={g.genre} className="flex justify-between text-xs">
                  <span className="text-gray-300 truncate">{g.genre}</span>
                  <span className="text-gray-500 ml-2 flex-shrink-0">
                    {Math.round(g.percentage * 100)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {topDetailedGenres.length > 0 && (
          <div>
            <Tip text={TIPS.detailed_genre} set={setTip}>
              <SectionTitle>Genre (detailed)</SectionTitle>
            </Tip>
            <div className="space-y-1">
              {topDetailedGenres.map((g) => (
                <div key={g.genre} className="flex justify-between text-xs">
                  <span className="text-gray-400 truncate">{g.genre}</span>
                  <span className="text-gray-500 ml-2 flex-shrink-0">
                    {Math.round(g.probability * 100)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {mbGenres.length > 0 && (
          <div>
            <Tip text={TIPS.mb_tags} set={setTip}>
              <SectionTitle>MB Tags</SectionTitle>
            </Tip>
            <div className="flex flex-wrap gap-1">
              {mbGenres.slice(0, 8).map((g) => (
                <span key={g} className="px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 text-[10px]">
                  {g}
                </span>
              ))}
            </div>
          </div>
        )}

      </div>
    </>
  );
}

// ─── Main UMAP view ───────────────────────────────────────────────────────────

interface Props { songs: Song[] }

const DEFAULT_X: FeatureValue = "danceability";
const DEFAULT_Y: FeatureValue = "bpm";

export function UmapView({ songs }: Props) {
  const [featureMode, setFeatureMode] = useState<FeatureMode>("all");

  const [pendingX, setPendingX] = useState<FeatureValue>(DEFAULT_X);
  const [pendingY, setPendingY] = useState<FeatureValue>(DEFAULT_Y);
  const [appliedX, setAppliedX] = useState<FeatureValue>(DEFAULT_X);
  const [appliedY, setAppliedY] = useState<FeatureValue>(DEFAULT_Y);
  const [appliedMode, setAppliedMode] = useState<FeatureMode>("all");

  const [umapData,       setUmapData]       = useState<UmapResponse | null>(null);
  const [loading,        setLoading]        = useState(false);
  const [error,          setError]          = useState<string | null>(null);
  const [selectedSongId, setSelectedSongId] = useState<string | null>(null);

  const songMap = useMemo(() => new Map(songs.map((s) => [s.id, s])), [songs]);

  const genreColorMap = useMemo(() => {
    const genres = new Set<string>();
    songs.forEach((s) => {
      const top = [...s.parent_genres].sort((a, b) => b.percentage - a.percentage)[0];
      if (top) genres.add(top.genre);
    });
    const map: Record<string, string> = {};
    [...genres].forEach((g, i) => { map[g] = GENRE_PALETTE[i % GENRE_PALETTE.length]; });
    return map;
  }, [songs]);

  const getPointColor = useCallback((songId: string): string => {
    const s = songMap.get(songId);
    if (!s) return GENRE_PALETTE[0];
    const top = [...s.parent_genres].sort((a, b) => b.percentage - a.percentage)[0];
    return top ? (genreColorMap[top.genre] ?? GENRE_PALETTE[0]) : GENRE_PALETTE[0];
  }, [songMap, genreColorMap]);

  const loadUmap = useCallback(async (features: string[]) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchUmap(features);
      setUmapData(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadUmap(ALL_FEATURE_VALUES); }, [loadUmap]);

  const applyFeatures = () => {
    setAppliedMode(featureMode);
    if (featureMode === "all") {
      loadUmap(ALL_FEATURE_VALUES);
    } else {
      setAppliedX(pendingX);
      setAppliedY(pendingY);
      loadUmap([pendingX, pendingY]);
    }
  };

  const xLabel2D = appliedMode === "custom" ? (FEATURE_LABEL[appliedX] ?? "") : "";
  const yLabel2D = appliedMode === "custom" ? (FEATURE_LABEL[appliedY] ?? "") : "";

  const selectedSong = selectedSongId ? songMap.get(selectedSongId) : null;

  const legendEntries = useMemo(() => {
    if (!umapData) return [];
    const present = new Set<string>();
    umapData.points_2d.forEach((p) => {
      const s = songMap.get(p.song_id);
      const top = s ? [...s.parent_genres].sort((a, b) => b.percentage - a.percentage)[0] : null;
      if (top) present.add(top.genre);
    });
    return [...present].map((g) => ({ genre: g, color: genreColorMap[g] ?? "#6b7280" }));
  }, [umapData, songMap, genreColorMap]);

  return (
    <div className="h-full flex overflow-hidden">

      {/* ── Left controls panel ── */}
      <div className="w-56 flex-shrink-0 border-r border-gray-800 flex flex-col">

        {/* Feature mode + selectors — scrollable */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          <div>
            <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
              Features
            </p>
            <div className="flex rounded overflow-hidden border border-gray-700 mb-3">
              {(["all", "custom"] as FeatureMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setFeatureMode(m)}
                  className={`flex-1 py-1 text-xs font-medium transition-colors capitalize ${
                    featureMode === m
                      ? "bg-indigo-600 text-white"
                      : "bg-gray-900 text-gray-400 hover:text-gray-200"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
            {featureMode === "all" && (
              <p className="text-[10px] text-gray-600 leading-snug">
                All 28 features — best for finding overall musical similarity clusters.
              </p>
            )}
          </div>

          {featureMode === "custom" && (
            <>
              <AxisSelect label="X" value={pendingX} onChange={setPendingX} />
              <AxisSelect label="Y" value={pendingY} onChange={setPendingY} />
            </>
          )}

          {legendEntries.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
                Color = Genre
              </p>
              <div className="space-y-1">
                {legendEntries.map(({ genre, color }) => (
                  <div key={genre} className="flex items-center gap-1.5">
                    <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                    <span className="text-[10px] text-gray-400 truncate">{genre}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Apply */}
        <div className="flex-shrink-0 px-4 pb-4 pt-2.5 border-t border-gray-800">
          <button
            onClick={applyFeatures}
            disabled={loading}
            className="w-full py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-800 disabled:text-gray-600 text-white text-xs font-semibold rounded transition-colors"
          >
            {loading ? "Computing…" : "Apply"}
          </button>
        </div>
      </div>

      {/* ── Center plot ── */}
      <div className="flex-1 overflow-hidden relative bg-gray-950">
        {loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center z-10 bg-gray-950/80">
            <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mb-3" />
            <p className="text-gray-400 text-sm">Computing UMAP…</p>
          </div>
        )}
        {error && !loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-red-400 text-sm">Error: {error}</p>
          </div>
        )}
        {!umapData && !loading && !error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-gray-600 text-sm">No data</p>
          </div>
        )}

        {umapData && (
          <UmapCanvas2D
            points={umapData.points_2d}
            selectedSongId={selectedSongId}
            getColor={getPointColor}
            onSelect={setSelectedSongId}
            xLabel={xLabel2D}
            yLabel={yLabel2D}
          />
        )}
      </div>

      {/* ── Right song info panel — scrollable ── */}
      <div className="w-72 flex-shrink-0 border-l border-gray-800 px-4 py-4 overflow-y-auto">
        {selectedSong ? (
          <SongInfoPanel song={selectedSong} />
        ) : (
          <div className="h-full flex flex-col items-center justify-center gap-2 text-center">
            <svg viewBox="0 0 24 24" className="w-8 h-8 text-gray-700" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="9" />
              <circle cx="12" cy="12" r="3" />
            </svg>
            <p className="text-gray-600 text-xs leading-relaxed">Click a point<br />to see song details</p>
          </div>
        )}
      </div>

    </div>
  );
}
