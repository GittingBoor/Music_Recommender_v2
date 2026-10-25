import { useEffect, useId, useState } from "react";
import { fetchSpotifyImport } from "../../services/api";
import type { SpotifyImport, SpotifyImportTrack } from "../../services/api";
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

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : DATE_FORMAT.format(date);
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

function FailedTrack({ track }: { readonly track: SpotifyImportTrack }) {
  return (
    <li className="flex items-baseline gap-3 border-b border-line py-1.5 last:border-b-0">
      <span className="w-6 shrink-0 text-right font-mono text-2xs text-ink-4 tabular-nums">{track.position + 1}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-ink">{track.title}</span>
        <span className="block truncate text-xs text-ink-3">{track.artists.join(", ")}</span>
        <span className="mt-0.5 block font-mono text-2xs"><ReasonLabel reason={track.reason} /></span>
      </span>
    </li>
  );
}

/** The tracks of one import that did not make it, loaded when opened. */
function FailedTracks({ importId, failedCount }: { readonly importId: number; readonly failedCount: number }) {
  const [tracks, setTracks] = useState<readonly SpotifyImportTrack[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reloads when the count changes while the panel is open (running import).
  useEffect(() => {
    let cancelled = false;
    fetchSpotifyImport(importId)
      .then((detail) => {
        if (cancelled) return;
        setTracks(detail.tracks.filter((t) => t.status === "failed"));
        setError(null);
      })
      .catch((err: unknown) => { if (!cancelled) setError(errorMessage(err)); });
    return () => { cancelled = true; };
  }, [importId, failedCount]);

  if (error) return <ErrorLine message={error} />;
  if (tracks === null) return <p className="py-1.5 font-mono text-2xs text-ink-3">Lade nicht übernommene Songs…</p>;
  return (
    <ul className="settle">
      {tracks.map((t) => <FailedTrack key={t.position} track={t} />)}
    </ul>
  );
}

function ImportRow({ imp }: { readonly imp: SpotifyImport }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const expandable = imp.failed > 0;

  const heading = (
    <span className="flex min-w-0 flex-1 items-baseline justify-between gap-3">
      <span className="truncate text-sm text-ink">{imp.name}</span>
      <span className="shrink-0 font-mono text-2xs text-ink-3 tabular-nums">{formatDate(imp.created_at)}</span>
    </span>
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
            <svg
              className={`h-2 w-2 shrink-0 self-center text-ink-3 group-hover:text-ink motion-safe:transition-transform ${open ? "rotate-90" : ""}`}
              viewBox="0 0 6 10" fill="none" stroke="currentColor" strokeWidth={1.4} aria-hidden="true"
            >
              <path d="M1 1l4 4-4 4" />
            </svg>
            {heading}
          </button>
        ) : (
          <div className="flex items-baseline gap-2">
            <span className="w-2 shrink-0" aria-hidden="true" />
            {heading}
          </div>
        )}
        <div className="space-y-2 pl-4">
          <ProgressBar imp={imp} />
          <CountLegend imp={imp} />
        </div>
      </div>
      {expandable && open && (
        <div id={panelId} className="mt-2.5 ml-4 border-t border-line pt-1">
          <FailedTracks importId={imp.id} failedCount={imp.failed} />
        </div>
      )}
    </li>
  );
}

/** Recent imports with their counts; failures expand per import. */
export function SpotifyImportList({ imports, error }: {
  readonly imports: readonly SpotifyImport[] | null;
  readonly error: string | null;
}) {
  return (
    <div className="space-y-2">
      <p className="t-label border-b border-line pb-1.5">Letzte Importe</p>
      {error && <ErrorLine message={error} />}
      {imports === null && !error && <p className="font-mono text-xs text-ink-3">Lade Importe…</p>}
      {imports?.length === 0 && (
        <p className="font-mono text-xs text-ink-3">Noch nichts importiert.</p>
      )}
      {imports && imports.length > 0 && (
        <ul className="-mt-2">
          {imports.map((imp) => <ImportRow key={imp.id} imp={imp} />)}
        </ul>
      )}
    </div>
  );
}
