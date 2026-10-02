import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import type { Song } from "../../types/song";
import type { UmapPoint2D, UmapResponse, UmapStatus } from "../../types/umap";
import type { PreviewSegment } from "../../services/api";
import { fetchPreviewSegment, fetchUmapStatus } from "../../services/api";
import { loadDefaultUmap } from "../../services/umapCache";
import { getSnapshot, playPreview, subscribe, toggle } from "../../audio/player";
import { Link, songPath } from "../../router";
import { UmapCanvas2D } from "./UmapCanvas2D";
import type { PlotAxes } from "./UmapCanvas2D";
import { COLOR, SERIES_EXTENDED } from "../../theme";

// ─── Feature definitions ──────────────────────────────────────────────────────

const FEATURE_OPTIONS = [
  { value: "bpm",                    label: "BPM",               group: "Rhythm",   rel: "dsp_features" },
  { value: "danceability",           label: "Danceability",      group: "Rhythm",   rel: "dsp_features" },
  { value: "beat_confidence",        label: "Beat Confidence",   group: "Rhythm",   rel: "dsp_features" },
  { value: "onset_rate",             label: "Onset Rate",        group: "Rhythm",   rel: "dsp_features" },
  { value: "key_strength",           label: "Key Strength",      group: "Tonal",    rel: "dsp_features" },
  { value: "chord_strength_mean",    label: "Chord Strength",    group: "Tonal",    rel: "dsp_features" },
  { value: "chord_change_rate",      label: "Chord Change Rate", group: "Tonal",    rel: "dsp_features" },
  { value: "integrated_lufs",        label: "Loudness (LUFS)",   group: "Loudness", rel: "dsp_features" },
  { value: "loudness_range_lu",      label: "Loudness Range",    group: "Loudness", rel: "dsp_features" },
  { value: "dynamic_complexity",     label: "Dyn. Complexity",   group: "Loudness", rel: "dsp_features" },
  { value: "loudness_db",            label: "Loudness (dB)",     group: "Loudness", rel: "dsp_features" },
  { value: "spectral_centroid_mean", label: "Spectral Centroid", group: "Spectral", rel: "dsp_features" },
  { value: "spectral_rolloff_mean",  label: "Spectral Rolloff",  group: "Spectral", rel: "dsp_features" },
  { value: "spectral_flux_mean",     label: "Spectral Flux",     group: "Spectral", rel: "dsp_features" },
  { value: "zero_crossing_rate",     label: "Zero Crossing",     group: "Spectral", rel: "dsp_features" },
  { value: "dissonance",             label: "Dissonance",        group: "Spectral", rel: "dsp_features" },
  { value: "happy",                  label: "Happy",             group: "Mood",     rel: "ml_moods"     },
  { value: "sad",                    label: "Sad",               group: "Mood",     rel: "ml_moods"     },
  { value: "aggressive",             label: "Aggressive",        group: "Mood",     rel: "ml_moods"     },
  { value: "party",                  label: "Party",             group: "Mood",     rel: "ml_moods"     },
  { value: "relaxed",                label: "Relaxed",           group: "Mood",     rel: "ml_moods"     },
  { value: "acoustic",               label: "Acoustic",          group: "Mood",     rel: "ml_moods"     },
  { value: "electronic",             label: "Electronic",        group: "Mood",     rel: "ml_moods"     },
  { value: "arousal",                label: "Arousal",           group: "Profile",  rel: "ml_profile"   },
  { value: "valence",                label: "Valence",           group: "Profile",  rel: "ml_profile"   },
  { value: "mainstream_score",       label: "Approachability",   group: "Profile",  rel: "ml_profile"   },
  { value: "active_score",           label: "Engagement",        group: "Profile",  rel: "ml_profile"   },
  { value: "vocal_score",            label: "Voice",             group: "Profile",  rel: "ml_profile"   },
] as const;

type FeatureValue = (typeof FEATURE_OPTIONS)[number]["value"];
type FeatureMode  = "all" | "custom";

const FEATURE_LABEL: Record<string, string> = Object.fromEntries(
  FEATURE_OPTIONS.map((o) => [o.value, o.label])
);
const FEATURE_GROUPS = [...new Set(FEATURE_OPTIONS.map((o) => o.group))];
const FEATURE_REL = Object.fromEntries(
  FEATURE_OPTIONS.map((o) => [o.value, o.rel])
) as Record<FeatureValue, (typeof FEATURE_OPTIONS)[number]["rel"]>;

/** Raw value of a feature — the same field the backend's FEATURE_DEFINITIONS reads. */
function featureValue(song: Song, key: FeatureValue): number | null {
  const rel = song[FEATURE_REL[key]] as unknown as Record<string, unknown> | null;
  const v = rel?.[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

const GENRE_PALETTE: readonly string[] = SERIES_EXTENDED;

// ─── Point size (remembered per browser) ─────────────────────────────────────

const POINT_SIZE_KEY = "umap.pointRadius";
const POINT_SIZE_MIN = 2;
const POINT_SIZE_MAX = 12;
const POINT_SIZE_DEFAULT = 3;

function storedPointSize(): number {
  try {
    const stored = parseInt(localStorage.getItem(POINT_SIZE_KEY) ?? "", 10);
    return stored >= POINT_SIZE_MIN && stored <= POINT_SIZE_MAX ? stored : POINT_SIZE_DEFAULT;
  } catch {
    return POINT_SIZE_DEFAULT; // storage unavailable
  }
}

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
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex-1 h-[3px] bg-line">
        <div className="h-full bg-ink-2" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-2xs text-ink-2 tabular-nums w-8 text-right flex-shrink-0">{pct}%</span>
    </div>
  );
}

/** Label | bar | percentage — one line per score. */
function ScoreRow({ label, value }: { label: React.ReactNode; value: number | null | undefined }) {
  return (
    <div className="grid grid-cols-[84px_1fr] items-center gap-2 min-h-[18px]">
      <span className="text-xs text-ink-3 truncate">{label}</span>
      {value != null ? (
        <Bar value={value} />
      ) : (
        <span className="font-mono text-2xs text-ink-4 text-right">—</span>
      )}
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

// Half the tooltip's max width (220px) plus a margin: keeps it on-screen near the edges.
const TIP_EDGE_PX = 118;

function TooltipPortal({ tip }: { tip: TooltipState | null }) {
  if (!tip) return null;
  return createPortal(
    <div
      className="fixed z-50 px-2 py-1.5 rounded-sm text-xs text-ink-2 bg-raised border border-line-strong leading-snug pointer-events-none max-w-[220px]"
      style={{
        left: `clamp(${TIP_EDGE_PX}px, ${tip.x}px, calc(100vw - ${TIP_EDGE_PX}px))`,
        top: tip.y,
        transform: "translate(-50%, -100%)",
      }}
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
    <div className="flex flex-col gap-1.5">
      <span className="t-label">
        {label} axis
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as FeatureValue)}
        className="field-select w-full h-7 text-xs"
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
    <p className="text-xs font-semibold text-ink mb-2.5">
      {children}
    </p>
  );
}

function Rule() {
  return <div className="border-t border-line" />;
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

  const { previewId, playing } = useSyncExternalStore(subscribe, getSnapshot);
  const [segment, setSegment] = useState<PreviewSegment | null>(null);
  const [tip,     setTip]     = useState<TooltipState | null>(null);

  const isPreviewing = previewId === song.id && playing;

  // The chorus position comes from the stored DSP timeseries, so it's cheap —
  // but only fetch it for the song actually being looked at.
  useEffect(() => {
    let cancelled = false;
    setSegment(null);
    if (!song.has_preview) return;
    fetchPreviewSegment(song.id)
      .then((s) => { if (!cancelled) setSegment(s); })
      .catch(() => { if (!cancelled) setSegment(null); });
    return () => { cancelled = true; };
  }, [song.id, song.has_preview]);

  const togglePreview = () => {
    if (!segment) return;
    if (isPreviewing) toggle(song.id);
    else playPreview(song.id, segment.start_seconds, segment.duration_seconds);
  };

  const danceabilityPct = dsp?.danceability != null
    ? `${Math.round(dsp.danceability * 100)}%`
    : "—";

  const keyDisplay = dsp?.key && dsp?.scale ? `${dsp.key} ${dsp.scale}` : "—";

  return (
    <>
      <TooltipPortal tip={tip} />
      <div className="flex flex-col gap-4 text-sm pb-2">

        {/* Title / Artist — right padding keeps clear of the phone close button */}
        <div className="pr-10 md:pr-0">
          <p className="text-xl font-semibold text-ink leading-[1.1] stretch-semi tracking-[-0.01em]">
            {song.title ?? "Unknown"}
          </p>
          <p className="text-base text-ink-2 mt-1.5 truncate">{song.artist ?? "Unknown Artist"}</p>
          {featuredArtists.length > 0 && (
            <p className="text-ink-3 text-xs mt-0.5">feat. {featuredArtists.join(", ")}</p>
          )}
          <Link to={songPath(song.id)} className="btn-quiet inline-block mt-2">
            Open song page →
          </Link>
        </div>

        {/* Chorus preview */}
        <div className="flex items-center gap-2.5">
          <div className="relative group">
            <button
              onClick={togglePreview}
              disabled={segment === null}
              aria-label={isPreviewing ? "Pause preview" : "Play preview"}
              className={`flex items-center justify-center w-8 h-8 rounded-sm border
                ${segment === null
                  ? "border-line text-ink-4 cursor-not-allowed"
                  : isPreviewing
                    ? "border-signal bg-signal text-ground"
                    : "border-line-strong text-ink hover:border-signal hover:text-signal cursor-pointer"}`}
            >
              {isPreviewing ? (
                <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="currentColor">
                  <rect x="3" y="2" width="4" height="12" />
                  <rect x="9" y="2" width="4" height="12" />
                </svg>
              ) : (
                <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="currentColor">
                  <path d="M4 2.5l10 5.5-10 5.5V2.5z" />
                </svg>
              )}
            </button>
            {segment === null && (
              <div className="pointer-events-none absolute left-10 top-1/2 -translate-y-1/2 hidden group-hover:flex z-20 whitespace-nowrap px-2 py-1 rounded-sm text-xs text-ink-2 bg-raised border border-line-strong">
                {song.has_preview ? "Locating chorus…" : "No audio file available"}
              </div>
            )}
          </div>
          <span className="font-mono text-2xs text-ink-3">
            {segment
              ? `${segment.duration_seconds}s hook from ${fmtDuration(segment.start_seconds)}`
              : song.has_preview ? "Locating chorus…" : "No preview"}
          </span>
        </div>

        <Rule />

        {/* Audio — four figures */}
        <div>
          <SectionTitle>Audio</SectionTitle>
          <div className="grid grid-cols-2 gap-x-4 gap-y-4">
            {(
              [
                ["BPM",         fmt(dsp?.bpm, 1),  "bpm"],
                ["Key",         keyDisplay,         "key"],
                ["Duration",    fmtDuration(song.file_metadata?.duration_seconds), "duration"],
                ["Danceability", danceabilityPct,   "danceability"],
              ] as [string, string, string][]
            ).map(([label, value, tipKey]) => (
              <div key={label} className="min-w-0">
                <Tip text={TIPS[tipKey]} set={setTip}>
                  <span className="t-label">{label}</span>
                </Tip>
                <p className="text-lg font-medium text-ink leading-none stretch-condensed tabular-nums mt-1.5 truncate">
                  {value}
                </p>
              </div>
            ))}
          </div>
        </div>

        <Rule />

        {/* Moods — all 7, bar or dash */}
        <div>
          <SectionTitle>Moods</SectionTitle>
          <div className="space-y-1.5">
            {MOODS.map(([label, key]) => (
              <ScoreRow
                key={key}
                label={<Tip text={TIPS[key as string]} set={setTip}><span>{label}</span></Tip>}
                value={moods?.[key]}
              />
            ))}
          </div>
        </div>

        <Rule />

        {/* Profile — arousal + valence + all profile fields */}
        <div>
          <SectionTitle>Profile</SectionTitle>
          <div className="space-y-1.5">
            <ScoreRow
              label={<Tip text={TIPS.arousal} set={setTip}><span>Arousal</span></Tip>}
              value={profile ? normalizeAV(profile.arousal) : null}
            />
            <ScoreRow
              label={<Tip text={TIPS.valence} set={setTip}><span>Valence</span></Tip>}
              value={profile ? normalizeAV(profile.valence) : null}
            />
          </div>

          {(
            [
              ["Approachability", TIPS.approachability, [["niche", profile?.niche_score], ["mainstream", profile?.mainstream_score]]],
              ["Engagement",      TIPS.engagement,      [["background", profile?.background_score], ["active", profile?.active_score]]],
              ["Voice",           TIPS.voice,           [["instrumental", profile?.instrumental_score], ["vocal", profile?.vocal_score]]],
              ["Gender",          TIPS.gender,          [["female", profile?.female_score], ["male", profile?.male_score]]],
            ] as [string, string, [string, number | null | undefined][]][]
          ).map(([title, tipText, pair]) => (
            <div key={title} className="mt-3.5">
              <Tip text={tipText} set={setTip}>
                <span className="t-label">{title}</span>
              </Tip>
              <div className="space-y-1.5 mt-1.5">
                {pair.map(([sub, value]) => (
                  <ScoreRow key={sub} label={sub} value={value} />
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Genres */}
        {(topGenres.length > 0 || topDetailedGenres.length > 0 || mbGenres.length > 0) && (
          <Rule />
        )}

        {topGenres.length > 0 && (
          <div>
            <Tip text={TIPS.parent_genre} set={setTip}>
              <SectionTitle>Genre (parent)</SectionTitle>
            </Tip>
            <div className="space-y-1">
              {topGenres.map((g) => (
                <div key={g.genre} className="flex justify-between gap-2 text-xs">
                  <span className="text-ink truncate">{g.genre}</span>
                  <span className="font-mono text-2xs text-ink-3 flex-shrink-0 tabular-nums">
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
                <div key={g.genre} className="flex justify-between gap-2 text-xs">
                  <span className="text-ink-2 truncate">{g.genre}</span>
                  <span className="font-mono text-2xs text-ink-3 flex-shrink-0 tabular-nums">
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
            <p className="text-xs text-ink-2 leading-relaxed">
              {mbGenres.slice(0, 8).map((g, i) => (
                <span key={g}>
                  {i > 0 && <span className="text-ink-4"> / </span>}
                  {g}
                </span>
              ))}
            </p>
          </div>
        )}

      </div>
    </>
  );
}

// ─── Fit progress ─────────────────────────────────────────────────────────────

const STATUS_POLL_MS = 1_000;
/** The bar never fills completely on an estimate; the map replacing it is the 100%. */
const MAX_ESTIMATED_PROGRESS = 0.95;

/** Polls the server-side fit while `active`; null until the first answer. */
function useUmapStatus(active: boolean): UmapStatus | null {
  const [status, setStatus] = useState<UmapStatus | null>(null);

  useEffect(() => {
    if (!active) {
      setStatus(null);
      return;
    }
    let cancelled = false;
    const poll = () => {
      fetchUmapStatus()
        .then((s) => { if (!cancelled) setStatus(s); })
        .catch(() => { /* the map request itself reports errors */ });
    };
    poll();
    const id = window.setInterval(poll, STATUS_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [active]);

  return status;
}

/** Loading overlay of the plot: a time-based estimate while the server fits, a sweep otherwise. */
function UmapLoading({ status }: { status: UmapStatus | null }) {
  const fitting = status?.phase === "fitting";
  const remaining = fitting ? Math.ceil(status.estimated_seconds - status.elapsed_seconds) : 0;
  const progress = fitting
    ? Math.min(MAX_ESTIMATED_PROGRESS, status.elapsed_seconds / status.estimated_seconds)
    : 0;

  return (
    <>
      <div className="absolute inset-x-0 top-0 h-[2px] overflow-hidden z-20">
        {fitting ? (
          <div
            className="h-full bg-signal transition-[width] duration-1000 ease-linear motion-reduce:transition-none"
            style={{ width: `${progress * 100}%` }}
            role="progressbar"
            aria-label="UMAP computation"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(progress * 100)}
          />
        ) : (
          <div className="sweep h-full w-1/4 bg-signal" />
        )}
      </div>
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 z-10 bg-ground/70">
        <p className="font-mono text-xs text-ink-2">Computing UMAP…</p>
        {fitting && (
          <p className="font-mono text-2xs text-ink-3 tabular-nums">
            {remaining > 0 ? `about ${remaining}s left` : "taking longer than last time"}
          </p>
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
  const [customX, setCustomX] = useState<FeatureValue>(DEFAULT_X);
  const [customY, setCustomY] = useState<FeatureValue>(DEFAULT_Y);

  const [umapData,       setUmapData]       = useState<UmapResponse | null>(null);
  const [loading,        setLoading]        = useState(false);
  const [error,          setError]          = useState<string | null>(null);
  const [selectedSongId, setSelectedSongId] = useState<string | null>(null);
  // Phones only: the legend panel is an overlay, the song panel a bottom sheet.
  const [showControls,   setShowControls]   = useState(false);

  const [hiddenGenres,   setHiddenGenres]   = useState<ReadonlySet<string>>(() => new Set());
  const [pointRadius,    setPointRadius]    = useState(storedPointSize);

  const changePointRadius = (r: number) => {
    setPointRadius(r);
    try { localStorage.setItem(POINT_SIZE_KEY, String(r)); } catch { /* storage unavailable */ }
  };

  const songMap = useMemo(() => new Map(songs.map((s) => [s.id, s])), [songs]);

  /** Strongest parent genre per song — drives colour, legend and hiding. */
  const topGenreById = useMemo(() => {
    const map = new Map<string, string>();
    songs.forEach((s) => {
      const top = [...s.parent_genres].sort((a, b) => b.percentage - a.percentage)[0];
      if (top) map.set(s.id, top.genre);
    });
    return map;
  }, [songs]);

  const genreColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    [...new Set(topGenreById.values())].forEach((g, i) => {
      map[g] = GENRE_PALETTE[i % GENRE_PALETTE.length];
    });
    return map;
  }, [topGenreById]);

  const getPointColor = useCallback((songId: string): string => {
    const genre = topGenreById.get(songId);
    return genre ? (genreColorMap[genre] ?? GENRE_PALETTE[0]) : GENRE_PALETTE[0];
  }, [topGenreById, genreColorMap]);

  const isPointVisible = useCallback((songId: string): boolean => {
    const genre = topGenreById.get(songId);
    return genre === undefined || !hiddenGenres.has(genre);
  }, [topGenreById, hiddenGenres]);

  // Only the newest request may write its result.
  const requestRef = useRef(0);
  const loadUmap = useCallback(async (request: Promise<UmapResponse>, showLoading: boolean) => {
    const id = ++requestRef.current;
    if (showLoading) setLoading(true);
    setError(null);
    try {
      const data = await request;
      if (id === requestRef.current) setUmapData(data);
    } catch (e) {
      if (id === requestRef.current) setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      if (id === requestRef.current) setLoading(false);
    }
  }, []);

  // The all-features UMAP is always loaded: custom mode borrows its neighbour
  // links. A grown library only refreshes the map in place, without the overlay.
  const songCount = songs.length;
  const loadedOnceRef = useRef(false);
  useEffect(() => {
    loadUmap(loadDefaultUmap(songCount), !loadedOnceRef.current);
    loadedOnceRef.current = true;
  }, [songCount, loadUmap]);

  const fitStatus = useUmapStatus(loading && featureMode === "all");

  // Custom mode is a plain scatter plot of raw values, computed right here;
  // songs missing either value are left out.
  const customPoints = useMemo((): UmapPoint2D[] => {
    const neighbors = new Map(umapData?.points_2d.map((p) => [p.song_id, p.neighbors]));
    const pts: UmapPoint2D[] = [];
    for (const s of songs) {
      const x = featureValue(s, customX);
      const y = featureValue(s, customY);
      if (x === null || y === null) continue;
      pts.push({
        song_id: s.id, x, y, title: s.title, artist: s.artist,
        neighbors: neighbors.get(s.id) ?? [],
      });
    }
    return pts;
  }, [songs, customX, customY, umapData]);

  const points = featureMode === "all" ? (umapData?.points_2d ?? null) : customPoints;

  const axes = useMemo((): PlotAxes | null => (
    featureMode === "custom" ? { x: FEATURE_LABEL[customX], y: FEATURE_LABEL[customY] } : null
  ), [featureMode, customX, customY]);

  const selectedSong = selectedSongId ? songMap.get(selectedSongId) : null;

  // Genres present on the current map, largest first.
  const legendEntries = useMemo(() => {
    const counts = new Map<string, number>();
    points?.forEach((p) => {
      const genre = topGenreById.get(p.song_id);
      if (genre) counts.set(genre, (counts.get(genre) ?? 0) + 1);
    });
    return [...counts]
      .sort((a, b) => b[1] - a[1])
      .map(([genre, count]) => ({ genre, count, color: genreColorMap[genre] ?? COLOR.ink4 }));
  }, [points, topGenreById, genreColorMap]);

  const visibleCount = useMemo(
    () => points?.filter((p) => isPointVisible(p.song_id)).length ?? 0,
    [points, isPointVisible]
  );

  const toggleGenre = (genre: string) => {
    setHiddenGenres((prev) => {
      const next = new Set(prev);
      if (!next.delete(genre)) next.add(genre);
      return next;
    });
  };
  const soloGenre = (genre: string) => {
    setHiddenGenres(new Set(legendEntries.map((e) => e.genre).filter((g) => g !== genre)));
  };
  const showAllGenres = () => setHiddenGenres(new Set());
  const hideAllGenres = () => setHiddenGenres(new Set(legendEntries.map((e) => e.genre)));

  return (
    <div className="h-full flex overflow-hidden relative">

      {/* ── Left controls panel (overlay on phones) ── */}
      <div className={`${showControls ? "flex" : "hidden"} md:flex absolute md:static inset-0 z-30 w-full md:w-64 flex-shrink-0 border-r border-line bg-panel flex-col`}>
        <button
          onClick={() => setShowControls(false)}
          className="btn md:hidden self-end m-2"
        >
          Close
        </button>

        {/* Feature mode + selectors — scrollable */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <div>
            <p className="t-label mb-2">
              Features
            </p>
            <div className="seg w-full mb-4">
              {(["all", "custom"] as FeatureMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setFeatureMode(m)}
                  aria-pressed={featureMode === m}
                  className={`seg-item capitalize ${featureMode === m ? "seg-item-on" : ""}`}
                >
                  {m}
                </button>
              ))}
            </div>
            {featureMode === "all" ? (
              <>
                <p className="text-sm font-semibold text-ink mb-1.5">
                  UMAP projection
                </p>
                <ul className="list-[square] pl-4 space-y-1 text-xs text-ink-2 leading-relaxed marker:text-ink-4">
                  <li>All 28 audio features squeezed into a 2D map</li>
                  <li>
                    <span className="text-ink">Distance = similarity</span> —
                    dots close together sound alike
                  </li>
                  <li>Axes have no unit, don't read values off them</li>
                </ul>
              </>
            ) : (
              <>
                <p className="text-sm font-semibold text-ink mb-1.5">
                  Scatter plot — not a UMAP
                </p>
                <ul className="list-[square] pl-4 space-y-1 text-xs text-ink-2 leading-relaxed marker:text-ink-4">
                  <li>Each song sits at its raw value for the two features you pick</li>
                  <li>
                    <span className="text-ink">Both axes are readable</span> —
                    unlike in UMAP mode
                  </li>
                </ul>
              </>
            )}
          </div>

          {featureMode === "custom" && (
            <div className="space-y-3 mt-4">
              <AxisSelect label="X" value={customX} onChange={setCustomX} />
              <AxisSelect label="Y" value={customY} onChange={setCustomY} />
              {songs.length > customPoints.length && (
                <p className="font-mono text-2xs text-ink-3">
                  {songs.length - customPoints.length} songs without a value left out
                </p>
              )}
            </div>
          )}

          <div className="mt-5 pt-4 border-t border-line">
            <div className="flex items-baseline justify-between mb-1.5">
              <label htmlFor="umap-point-size" className="text-xs font-semibold text-ink">
                Point size
              </label>
              <span className="font-mono text-2xs text-ink-3 tabular-nums">{pointRadius}</span>
            </div>
            <input
              id="umap-point-size"
              type="range"
              min={POINT_SIZE_MIN}
              max={POINT_SIZE_MAX}
              step={1}
              value={pointRadius}
              onChange={(e) => changePointRadius(Number(e.target.value))}
              className="range w-full"
            />
          </div>

          <div className="mt-5 pt-4 border-t border-line">
            <p className="text-xs font-semibold text-ink mb-1.5">
              Lines = Similarity
            </p>
            <ul className="list-[square] pl-4 space-y-1 text-xs text-ink-2 leading-relaxed marker:text-ink-4">
              <li>Each song links to its 5 nearest neighbours</li>
              <li>
                {featureMode === "all"
                  ? "Measured on all features, before the 2D projection"
                  : "Measured on all features, not just the two axes"}
              </li>
              <li><span className="text-ink">Hover</span> a dot for a faint preview</li>
              <li><span className="text-ink">Click</span> it to pin the lines</li>
            </ul>
          </div>

          {legendEntries.length > 0 && (
            <div className="mt-5 pt-4 border-t border-line">
              <div className="flex items-baseline justify-between mb-1.5">
                <p className="text-xs font-semibold text-ink">
                  Color = Genre
                </p>
                <div className="flex gap-3">
                  <button onClick={showAllGenres} disabled={hiddenGenres.size === 0} className="btn-quiet">
                    All
                  </button>
                  <button onClick={hideAllGenres} disabled={visibleCount === 0} className="btn-quiet">
                    None
                  </button>
                </div>
              </div>
              <p className="font-mono text-2xs text-ink-3 mb-2 tabular-nums">
                {hiddenGenres.size > 0
                  ? `${visibleCount} of ${points?.length ?? 0} songs shown`
                  : "Click a genre to hide it"}
              </p>
              <ul className="space-y-px">
                {legendEntries.map(({ genre, count, color }) => {
                  const hidden = hiddenGenres.has(genre);
                  return (
                    <li key={genre} className="group flex items-center gap-2">
                      <button
                        onClick={() => toggleGenre(genre)}
                        aria-pressed={!hidden}
                        title={hidden ? "Show genre" : "Hide genre"}
                        className="flex-1 min-w-0 flex items-center gap-2 py-0.5 text-left"
                      >
                        <span
                          className="w-2 h-2 flex-shrink-0 border"
                          style={{ borderColor: color, backgroundColor: hidden ? "transparent" : color }}
                        />
                        <span className={`text-xs truncate ${hidden ? "text-ink-4 line-through" : "text-ink-2 group-hover:text-ink"}`}>
                          {genre}
                        </span>
                        <span className="ml-auto font-mono text-2xs text-ink-4 tabular-nums">{count}</span>
                      </button>
                      <button
                        onClick={() => soloGenre(genre)}
                        title="Show only this genre"
                        className="font-mono text-2xs text-ink-3 hover:text-ink md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100"
                      >
                        only
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>

      </div>

      {/* ── Center plot ── */}
      <div className="flex-1 overflow-hidden relative bg-ground">
        <button
          onClick={() => setShowControls(true)}
          className="btn md:hidden absolute top-2 left-2 z-20 bg-panel/90"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <line x1="4" y1="6" x2="20" y2="6" /><line x1="4" y1="12" x2="20" y2="12" /><line x1="4" y1="18" x2="20" y2="18" />
          </svg>
          {featureMode === "all" ? "UMAP" : "Custom"} · Legend
        </button>
        {/* Custom mode doesn't wait for the UMAP — it only lacks lines meanwhile */}
        {featureMode === "all" && loading && <UmapLoading status={fitStatus} />}
        {featureMode === "all" && error && !loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="font-mono text-xs text-bad">Error: {error}</p>
          </div>
        )}
        {points?.length === 0 || (!points && !loading && !error) ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="font-mono text-xs text-ink-3">No data</p>
          </div>
        ) : null}

        {points && points.length > 0 && (
          <UmapCanvas2D
            points={points}
            selectedSongId={selectedSongId}
            getColor={getPointColor}
            isVisible={isPointVisible}
            onSelect={setSelectedSongId}
            pointRadius={pointRadius}
            axes={axes}
          />
        )}
      </div>

      {/* ── Right song info panel — scrollable ── */}
      <div className={`${selectedSong ? "block" : "hidden"} md:block absolute md:static inset-x-0 bottom-0 z-20 max-h-[55%] md:max-h-none bg-panel border-t md:border-t-0 md:border-l border-line shadow-2xl md:shadow-none md:w-72 flex-shrink-0 px-4 py-4 md:px-5 md:py-5 overflow-y-auto`}>
        {selectedSong && (
          <button
            onClick={() => setSelectedSongId(null)}
            className="btn md:hidden absolute top-3 right-3 z-10 w-8 h-8 px-0"
            aria-label="Close song details"
          >
            ✕
          </button>
        )}
        {selectedSong ? (
          <SongInfoPanel song={selectedSong} />
        ) : (
          <div className="h-full flex items-center justify-center text-center">
            <p className="font-mono text-2xs text-ink-3 leading-relaxed">Click a point<br />to see song details</p>
          </div>
        )}
      </div>

    </div>
  );
}
