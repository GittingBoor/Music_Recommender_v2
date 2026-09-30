import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import type { Song } from "../../types/song";
import type { UmapResponse, UmapStatus } from "../../types/umap";
import type { PreviewSegment } from "../../services/api";
import { fetchPreviewSegment, fetchUmap, fetchUmapStatus } from "../../services/api";
import { loadDefaultUmap } from "../../services/umapCache";
import { getSnapshot, playPreview, subscribe, toggle } from "../../audio/player";
import { Link, songPath } from "../../router";
import { UmapCanvas2D } from "./UmapCanvas2D";
import { COLOR, SERIES_EXTENDED } from "../../theme";

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

const FEATURE_LABEL: Record<string, string> = Object.fromEntries(
  FEATURE_OPTIONS.map((o) => [o.value, o.label])
);
const FEATURE_GROUPS = [...new Set(FEATURE_OPTIONS.map((o) => o.group))];

const GENRE_PALETTE: readonly string[] = SERIES_EXTENDED;

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

  // Changes apply immediately — switching mode or swapping an axis reloads.
  // A grown library only refreshes the map in place, without the loading overlay.
  const songCount = songs.length;
  const shownModeRef = useRef<string | null>(null);
  useEffect(() => {
    const mode = featureMode === "all" ? "all" : `${customX}/${customY}`;
    const modeChanged = shownModeRef.current !== mode;
    shownModeRef.current = mode;
    if (featureMode === "all") loadUmap(loadDefaultUmap(songCount), modeChanged);
    else loadUmap(fetchUmap([customX, customY]), modeChanged);
  }, [featureMode, customX, customY, songCount, loadUmap]);

  const fitStatus = useUmapStatus(loading && featureMode === "all");

  const xLabel2D = featureMode === "custom" ? (FEATURE_LABEL[customX] ?? "") : "";
  const yLabel2D = featureMode === "custom" ? (FEATURE_LABEL[customY] ?? "") : "";

  const selectedSong = selectedSongId ? songMap.get(selectedSongId) : null;

  const legendEntries = useMemo(() => {
    if (!umapData) return [];
    const present = new Set<string>();
    umapData.points_2d.forEach((p) => {
      const s = songMap.get(p.song_id);
      const top = s ? [...s.parent_genres].sort((a, b) => b.percentage - a.percentage)[0] : null;
      if (top) present.add(top.genre);
    });
    return [...present].map((g) => ({ genre: g, color: genreColorMap[g] ?? COLOR.ink4 }));
  }, [umapData, songMap, genreColorMap]);

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
            </div>
          )}

          <div className="mt-5 pt-4 border-t border-line">
            <p className="text-xs font-semibold text-ink mb-1.5">
              Lines = Similarity
            </p>
            <ul className="list-[square] pl-4 space-y-1 text-xs text-ink-2 leading-relaxed marker:text-ink-4">
              <li>Each song links to its 5 nearest neighbours</li>
              <li>Measured on all features, before the 2D projection</li>
              <li><span className="text-ink">Hover</span> a dot for a faint preview</li>
              <li><span className="text-ink">Click</span> it to pin the lines</li>
            </ul>
          </div>

          {legendEntries.length > 0 && (
            <div className="mt-5 pt-4 border-t border-line">
              <p className="text-xs font-semibold text-ink mb-2">
                Color = Genre
              </p>
              <div className="space-y-1">
                {legendEntries.map(({ genre, color }) => (
                  <div key={genre} className="flex items-center gap-2">
                    <div className="w-2 h-2 flex-shrink-0" style={{ backgroundColor: color }} />
                    <span className="text-xs text-ink-2 truncate">{genre}</span>
                  </div>
                ))}
              </div>
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
        {loading && <UmapLoading status={fitStatus} />}
        {error && !loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="font-mono text-xs text-bad">Error: {error}</p>
          </div>
        )}
        {!umapData && !loading && !error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="font-mono text-xs text-ink-3">No data</p>
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
