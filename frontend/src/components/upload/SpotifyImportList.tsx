import { useEffect, useId, useState } from "react";
import type { ReactNode } from "react";
import { fetchSpotifyImport, retrySpotifyImport } from "../../services/api";
import type { SpotifyImport, SpotifyImportTrack } from "../../services/api";
import { Link, songPath } from "../../router";
import { ErrorLine, errorMessage } from "../Notice";

const REASON_LABEL: Readonly<Record<string, string>> = {
  spotify_mismatch:      "Erkannte Aufnahme ist ein anderer Song",
  no_fitting_hit:        "Kein passendes YouTube-Video",
  search_error:          "YouTube-Suche fehlgeschlagen",
  no_acoustid_match:     "Nicht erkannt",
  needs_metadata:        "Titel und Künstler fehlen",
  too_long_unrecognized: "Zu lang (unbekannt)",
  cancelled:             "Abgebrochen",
};

interface Count {
  readonly key: keyof Pick<SpotifyImport, "saved" | "duplicate" | "failed" | "queued">;
  readonly label: string;
  /** Dot and bar segment colour. */
  readonly tone: string;
}

// Order of the bar segments and the legend below it.
const COUNTS: readonly Count[] = [
  { key: "saved",     label: "übernommen",        tone: "bg-ok" },
  { key: "duplicate", label: "schon vorhanden",   tone: "bg-ink-3" },
  { key: "failed",    label: "nicht übernommen",  tone: "bg-bad" },
  { key: "queued",    label: "in Arbeit",         tone: "bg-signal" },
];

const DATE_FORMAT = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
});

const TIME_FORMAT = new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit" });

const MS_PER_MINUTE = 60_000;
const MINUTES_PER_HOUR = 60;
const MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR;
// Keeps "läuft seit …" fresh between polls.
const ELAPSED_TICK_MS = 30_000;

/** Compact duration: "< 1 min", "42 min", "3 h 05 min", "1 T 2 h". */
function formatDuration(ms: number): string {
  const minutes = Math.floor(Math.max(ms, 0) / MS_PER_MINUTE);
  if (minutes < 1) return "< 1 min";
  if (minutes < MINUTES_PER_HOUR) return `${minutes} min`;
  if (minutes < MINUTES_PER_DAY) {
    const rest = String(minutes % MINUTES_PER_HOUR).padStart(2, "0");
    return `${Math.floor(minutes / MINUTES_PER_HOUR)} h ${rest} min`;
  }
  const hours = Math.floor((minutes % MINUTES_PER_DAY) / MINUTES_PER_HOUR);
  return `${Math.floor(minutes / MINUTES_PER_DAY)} T ${hours} h`;
}

/** "25.10.26, 17:11 – 18:02" on the same day, the full end date otherwise. */
function formatRange(start: Date, end: Date): string {
  const sameDay = start.toDateString() === end.toDateString();
  return `${DATE_FORMAT.format(start)} – ${sameDay ? TIME_FORMAT.format(end) : DATE_FORMAT.format(end)}`;
}

/** Current time, re-read every ELAPSED_TICK_MS while `active`. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), ELAPSED_TICK_MS);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

/** When the import ran and how long it took; elapsed time while it still runs. */
function ImportTiming({ imp }: { readonly imp: SpotifyImport }) {
  const running = imp.finished_at === null;
  const now = useNow(running);
  const start = new Date(imp.created_at);
  const end = new Date(imp.finished_at ?? now);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;

  const approx = imp.finished_estimated ? "ca. " : "";
  const elapsed = formatDuration(end.getTime() - start.getTime());
  const when = running ? `seit ${DATE_FORMAT.format(start)}` : formatRange(start, end);
  const duration = running ? `läuft ${elapsed}` : `${approx}${elapsed}`;

  return (
    <p className="flex flex-wrap justify-between gap-x-3 font-mono text-2xs text-ink-3 tabular-nums">
      <span className="whitespace-nowrap">{when}</span>
      <span className={`whitespace-nowrap ${running ? "text-ink-2" : ""}`}>{duration}</span>
    </p>
  );
}

/** Where the import's tracks are: one bar, segments in COUNTS order; queued stays empty. */
function ProgressBar({ imp }: { readonly imp: SpotifyImport }) {
  const total = Math.max(imp.total, 1);
  return (
    <div className="flex h-[2px] bg-line" aria-hidden="true">
      {COUNTS.filter((c) => c.key !== "queued").map((c) => (
        <div
          key={c.key}
          className={`${c.tone} h-full motion-safe:transition-[width] motion-safe:duration-500`}
          style={{ width: `${(imp[c.key] / total) * 100}%` }}
        />
      ))}
    </div>
  );
}

function CountLegend({ imp }: { readonly imp: SpotifyImport }) {
  return (
    <ul className="flex flex-wrap gap-x-3.5 gap-y-1 font-mono text-2xs tabular-nums">
      {COUNTS.map((c) => {
        const n = imp[c.key];
        const live = c.key === "queued" && n > 0;
        return (
          <li key={c.key} className={`flex items-center gap-1.5 whitespace-nowrap ${n > 0 ? "text-ink-2" : "text-ink-4"}`}>
            <span className={`h-1.5 w-1.5 shrink-0 ${n > 0 ? c.tone : "bg-line-strong"} ${live ? "animate-pulse" : ""}`} />
            <span><span className={n > 0 ? "text-ink" : ""}>{n}</span> {c.label}</span>
          </li>
        );
      })}
    </ul>
  );
}

function ReasonLabel({ reason }: { readonly reason: string | null }) {
  const label = reason ? REASON_LABEL[reason] : undefined;
  if (label) return <span className="text-ink-2">{label}</span>;
  return (
    <span className="text-ink-2">
      Fehler{reason && <span className="ml-1.5 text-ink-4 break-all">{reason}</span>}
    </span>
  );
}

/** Right-pointing triangle that turns down when `open`. */
function Chevron({ open }: { readonly open: boolean }) {
  return (
    <svg
      className={`h-2 w-2 shrink-0 self-center text-ink-3 group-hover:text-ink motion-safe:transition-transform ${open ? "rotate-90" : ""}`}
      viewBox="0 0 6 10" fill="none" stroke="currentColor" strokeWidth={1.4} aria-hidden="true"
    >
      <path d="M1 1l4 4-4 4" />
    </svg>
  );
}

function TrackRow({ track }: { readonly track: SpotifyImportTrack }) {
  const title = track.song_id
    ? (
      <Link
        to={songPath(track.song_id)}
        className="block truncate text-sm text-ink underline decoration-line-strong underline-offset-4 hover:decoration-ink-3"
        title="In der Bibliothek öffnen"
      >
        {track.title}
      </Link>
    )
    : <span className="block truncate text-sm text-ink">{track.title}</span>;
  return (
    <li className="flex items-baseline gap-3 border-b border-line py-1.5 last:border-b-0">
      <span className="w-6 shrink-0 text-right font-mono text-2xs text-ink-4 tabular-nums">{track.position + 1}</span>
      <span className="min-w-0 flex-1">
        {title}
        <span className="block truncate text-xs text-ink-3">{track.artists.join(", ")}</span>
        {track.status === "failed" && (
          <span className="mt-0.5 block font-mono text-2xs"><ReasonLabel reason={track.reason} /></span>
        )}
      </span>
    </li>
  );
}

/** One status of an import's tracks behind its own toggle. */
function TrackGroup({ count, tracks, defaultOpen, children }: {
  readonly count: Count;
  readonly tracks: readonly SpotifyImportTrack[];
  readonly defaultOpen: boolean;
  readonly children?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  return (
    <li className="border-b border-line last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className="group flex w-full items-center gap-2 py-1.5 text-left font-mono text-2xs tabular-nums text-ink-2 hover:text-ink"
      >
        <Chevron open={open} />
        <span className={`h-1.5 w-1.5 shrink-0 ${count.tone}`} />
        <span><span className="text-ink">{tracks.length}</span> {count.label}</span>
      </button>
      {open && (
        <div id={panelId} className="pb-1.5 pl-4">
          {children}
          <ul className="settle">
            {tracks.map((t) => <TrackRow key={t.position} track={t} />)}
          </ul>
        </div>
      )}
    </li>
  );
}

/** Every track of one import grouped by status, loaded when opened. */
function ImportTracks({ imp, onRetried }: {
  readonly imp: SpotifyImport;
  readonly onRetried: (changed: SpotifyImport) => void;
}) {
  const [tracks, setTracks] = useState<readonly SpotifyImportTrack[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reloads when a count changes while the panel is open (running import).
  useEffect(() => {
    let cancelled = false;
    fetchSpotifyImport(imp.id)
      .then((detail) => {
        if (cancelled) return;
        setTracks(detail.tracks);
        setError(null);
      })
      .catch((err: unknown) => { if (!cancelled) setError(errorMessage(err)); });
    return () => { cancelled = true; };
  }, [imp.id, imp.saved, imp.duplicate, imp.failed, imp.queued]);

  if (error) return <ErrorLine message={error} />;
  if (tracks === null) return <p className="py-1.5 font-mono text-2xs text-ink-3">Lade Songs…</p>;
  return (
    <ul>
      {COUNTS.map((c) => {
        const group = tracks.filter((t) => t.status === c.key);
        if (group.length === 0) return null;
        return (
          <TrackGroup key={c.key} count={c} tracks={group} defaultOpen={c.key === "failed"}>
            {c.key === "failed" && <RetryFailed importId={imp.id} onRetried={onRetried} />}
          </TrackGroup>
        );
      })}
    </ul>
  );
}

/** Re-queues the failed tracks; the returned import replaces the row right away. */
function RetryFailed({ importId, onRetried }: {
  readonly importId: number;
  readonly onRetried: (changed: SpotifyImport) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function retry(): Promise<void> {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      onRetried(await retrySpotifyImport(importId));
    } catch (err: unknown) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 border-b border-line py-2">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <button
          type="button"
          onClick={() => { void retry(); }}
          disabled={busy}
          aria-busy={busy}
          className="font-mono text-2xs text-ink-2 underline decoration-line-strong underline-offset-4 hover:text-ink hover:decoration-ink-3 disabled:cursor-wait disabled:text-ink-3 disabled:no-underline"
        >
          {busy ? "Wird neu eingereiht…" : "Fehlgeschlagene erneut versuchen"}
        </button>
        <span className="text-xs text-ink-3">Sucht die Songs erneut, auch über YouTube Music.</span>
      </div>
      {error && <ErrorLine message={error} />}
    </div>
  );
}

function ImportRow({ imp, onChanged }: {
  readonly imp: SpotifyImport;
  readonly onChanged: (changed: SpotifyImport) => void;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const expandable = imp.total > 0;

  const heading = (
    <span className="min-w-0 flex-1 truncate text-sm text-ink">{imp.name}</span>
  );

  return (
    <li className="border-b border-line py-3">
      <div className="space-y-2">
        {expandable ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls={panelId}
            className="group flex w-full items-baseline gap-2 text-left"
          >
            <Chevron open={open} />
            {heading}
          </button>
        ) : (
          <div className="flex items-baseline gap-2">
            <span className="w-2 shrink-0" aria-hidden="true" />
            {heading}
          </div>
        )}
        <div className="space-y-2 pl-4">
          <ImportTiming imp={imp} />
          <ProgressBar imp={imp} />
          <CountLegend imp={imp} />
        </div>
      </div>
      {expandable && open && (
        <div id={panelId} className="mt-2.5 ml-4 border-t border-line pt-1">
          <ImportTracks imp={imp} onRetried={(changed) => { setOpen(false); onChanged(changed); }} />
        </div>
      )}
    </li>
  );
}

/** Recent imports with their counts; each expands to its tracks, grouped by status. */
export function SpotifyImportList({ imports, error, onChanged }: {
  readonly imports: readonly SpotifyImport[] | null;
  readonly error: string | null;
  readonly onChanged: (changed: SpotifyImport) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="t-label border-b border-line pb-1.5">Letzte Importe</p>
      {error && <ErrorLine message={error} />}
      {imports === null && !error && <p className="font-mono text-xs text-ink-3">Lade Importe…</p>}
      {imports && imports.length > 0 && (
        <ul className="-mt-2">
          {imports.map((imp) => <ImportRow key={imp.id} imp={imp} onChanged={onChanged} />)}
        </ul>
      )}
    </div>
  );
}
