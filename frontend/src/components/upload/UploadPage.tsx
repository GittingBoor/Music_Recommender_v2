import { useRef, useState } from "react";
import { uploadSong } from "../../services/api";
import type { UploadResult, YoutubeErrorDetail } from "../../services/api";
import { PlayButton } from "../PlayButton";
import { StatCard } from "../StatCard";
import { YoutubeSearch } from "./YoutubeSearch";
import { PipelineList } from "./PipelineList";

// ── types ─────────────────────────────────────────────────────────────────
type ItemStatus = "pending" | "processing" | "done";

interface QueueItem {
  name: string;
  file?: File;
  status: ItemStatus;
  result?: UploadResult;
}

// ── helpers ───────────────────────────────────────────────────────────────
const SUPPORTED_EXTS = new Set([".wav", ".mp3", ".flac", ".ogg", ".aiff", ".m4a"]);

function ext(filename: string): string {
  return filename.slice(filename.lastIndexOf(".")).toLowerCase();
}

function isSupported(file: File): boolean {
  return SUPPORTED_EXTS.has(ext(file.name));
}

const REASON_LABEL: Record<string, string> = {
  duplicate:            "Bereits vorhanden",
  no_acoustid_match:    "Kein AcoustID-Treffer",
  too_long_unrecognized:"Zu lang (unbekannt)",
  unsupported_format:   "Format nicht unterstützt",
  error:                "Fehler",
};

function reasonLabel(reason: string | null): string {
  if (!reason) return "";
  return REASON_LABEL[reason] ?? reason;
}

const BADGE_DOT: Record<string, string> = {
  saved:   "bg-ok",
  skipped: "bg-warn",
  error:   "bg-bad",
};

const SCOPE_LABEL: Record<string, string> = {
  video:  "Betrifft nur dieses Video",
  global: "Betrifft alle Downloads",
};

/** Sits at the very top of the page — errors down in the list get missed. */
function ErrorBanner({ detail, onDismiss }: {
  detail: YoutubeErrorDetail;
  onDismiss: () => void;
}) {
  const [showRaw, setShowRaw] = useState(false);

  return (
    <div className="border-l-2 border-bad bg-bad/[0.06] pl-4 pr-3 py-3">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3 flex-wrap">
            <p className="text-sm font-semibold text-ink">{detail.title}</p>
            {SCOPE_LABEL[detail.scope] && (
              <span className="font-mono text-2xs text-bad">
                {SCOPE_LABEL[detail.scope]}
              </span>
            )}
          </div>

          <p className="text-xs text-ink-2 leading-relaxed mt-1.5 max-w-2xl">
            {detail.explanation}
          </p>

          {detail.raw_message && (
            <>
              <button
                onClick={() => setShowRaw((v) => !v)}
                className="btn-quiet mt-2"
              >
                {showRaw ? "Originalmeldung ausblenden" : "Originalmeldung anzeigen"}
              </button>
              {showRaw && (
                <pre className="mt-1.5 p-2 bg-ground border border-line font-mono text-2xs text-ink-2 whitespace-pre-wrap break-all">
                  {detail.raw_message}
                </pre>
              )}
            </>
          )}
        </div>

        <button
          onClick={onDismiss}
          aria-label="Schließen"
          className="text-ink-3 hover:text-ink shrink-0 w-6 h-6 flex items-center justify-center"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="square" d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>
    </div>
  );
}

// ── component ─────────────────────────────────────────────────────────────
export function UploadPage() {
  const [queue, setQueue]     = useState<QueueItem[]>([]);
  const [running, setRunning] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError]     = useState<YoutubeErrorDetail | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── add files ────────────────────────────────────────────────────────
  function addFiles(files: FileList | File[]) {
    const arr = Array.from(files);
    const items: QueueItem[] = arr.map((file) => ({
      name: file.name,
      file,
      status: "pending" as const,
      result: isSupported(file)
        ? undefined
        : {
            status: "skipped",
            reason: "unsupported_format",
            title: null,
            artist: null,
            song_id: null,
            filename: file.name,
          },
    }));
    setQueue((prev) => [...prev, ...items]);
  }

  // ── add a finished YouTube download ──────────────────────────────────
  function addYoutubeResult(result: UploadResult) {
    setQueue((prev) => [
      ...prev,
      {
        name: result.title ?? result.filename,
        status: "done" as const,
        result,
      },
    ]);
  }

  // ── drag&drop ────────────────────────────────────────────────────────
  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(true);
  }
  function onDragLeave() {
    setDragOver(false);
  }
  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  }

  // ── process queue ────────────────────────────────────────────────────
  async function processQueue(items: QueueItem[]) {
    setRunning(true);
    for (let i = 0; i < items.length; i++) {
      const item = items[i];

      // Already resolved client-side (unsupported format) or no file
      // to upload (e.g. a YouTube download added directly to the queue).
      if (item.result || !item.file) continue;

      // Mark as processing
      setQueue((prev) =>
        prev.map((q, idx) => (idx === i ? { ...q, status: "processing" } : q))
      );

      let result: UploadResult;
      try {
        result = await uploadSong(item.file);
      } catch (err: unknown) {
        result = {
          status: "error",
          reason: err instanceof Error ? err.message : String(err),
          title: null,
          artist: null,
          song_id: null,
          filename: item.name,
        };
      }

      setQueue((prev) =>
        prev.map((q, idx) =>
          idx === i ? { ...q, status: "done", result } : q
        )
      );
    }
    setRunning(false);
  }

  // ── derived state ────────────────────────────────────────────────────
  const doneItems  = queue.filter((q) => q.status === "done" || q.result);
  const allDone    = queue.length > 0 && queue.every((q) => q.status === "done" || q.result);
  const doneCount  = doneItems.length;
  const totalCount = queue.length;
  const progress   = totalCount > 0 ? (doneCount / totalCount) * 100 : 0;

  const saved   = doneItems.filter((q) => q.result?.status === "saved").length;
  const skipped = doneItems.filter((q) => q.result?.status === "skipped").length;
  const errors  = doneItems.filter((q) => q.result?.status === "error").length;

  const reasonCounts = doneItems.reduce<Record<string, number>>((acc, q) => {
    const r = q.result?.reason;
    if (r) { acc[r] = (acc[r] ?? 0) + 1; }
    return acc;
  }, {});

  // Compute the actual queue with client-side-resolved items marked done
  const displayQueue: QueueItem[] = queue.map((q) => ({
    ...q,
    status: q.result ? "done" : q.status,
  }));

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto px-6 pt-6 pb-16 space-y-8">

        {/* ── error banner, always at the top ──────────────────────── */}
        {error && <ErrorBanner detail={error} onDismiss={() => setError(null)} />}

        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_380px] gap-x-12 gap-y-12">

          {/* ── youtube search ─────────────────────────────────────── */}
          <section className="min-w-0">
            <h2 className="t-section mb-4">YouTube</h2>
            <YoutubeSearch onDownloaded={addYoutubeResult} onError={setError} />
          </section>

          {/* ── file upload + everything processed in this session ── */}
          <section className="min-w-0 space-y-6 lg:border-l lg:border-line lg:pl-12">
            <h2 className="t-section">Datei hochladen</h2>

            {/* ── drop zone ────────────────────────────────────────── */}
            <div
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              onClick={() => !running && inputRef.current?.click()}
              className={`
                border border-dashed px-6 py-10 flex flex-col items-center
                gap-2 cursor-pointer select-none transition-colors
                ${dragOver
                  ? "border-signal bg-signal/5"
                  : "border-line-strong hover:border-ink-4 hover:bg-raised/40"}
                ${running ? "pointer-events-none opacity-60" : ""}
              `}
            >
              <svg
                className={`w-6 h-6 mb-1 ${dragOver ? "text-signal" : "text-ink-3"} transition-colors`}
                viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}
              >
                <path strokeLinecap="square"
                  d="M3 16.5v4.5h18v-4.5M7.5 7.5L12 3m0 0l4.5 4.5M12 3v13.5" />
              </svg>
              <p className="text-sm text-ink-2 text-center">
                MP3-Dateien hier ablegen oder klicken zum Auswählen
              </p>
              <p className="font-mono text-2xs text-ink-3">
                mp3 · wav · flac · ogg · aiff · m4a
              </p>
              <input
                ref={inputRef}
                type="file"
                multiple
                accept="audio/*"
                className="hidden"
                onChange={(e) => e.target.files && addFiles(e.target.files)}
              />
            </div>

            {/* ── action bar ───────────────────────────────────────── */}
            {queue.length > 0 && (
              <div className="flex items-center gap-3">
                {!running && !allDone && (
                  <button
                    onClick={() => processQueue(displayQueue)}
                    className="btn btn-primary h-8 px-3"
                  >
                    {queue.filter((q) => !q.result).length} Dateien verarbeiten
                  </button>
                )}
                {running && (
                  <span className="font-mono text-xs text-ink-2 animate-pulse">
                    Verarbeite…
                  </span>
                )}
                <button
                  onClick={() => { setQueue([]); setRunning(false); }}
                  disabled={running}
                  className="btn h-8 px-3"
                >
                  Zurücksetzen
                </button>
              </div>
            )}

            {/* ── progress bar ─────────────────────────────────────── */}
            {queue.length > 0 && (
              <div className="space-y-1.5">
                <div className="flex justify-between font-mono text-2xs text-ink-3">
                  <span><span className="text-ink">{doneCount}</span> / {totalCount} erledigt</span>
                  {allDone && <span className="text-ok">Fertig</span>}
                </div>
                <div className="h-[2px] bg-line">
                  <div
                    className="h-full bg-signal transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}

            {/* ── statistics (shown once all done) ─────────────────── */}
            {allDone && (
              <div className="space-y-5">
                <div className="grid grid-cols-4 border-y border-line-strong">
                  <StatCard label="Gesamt"     value={String(totalCount)} />
                  <StatCard label="Gespeichert" value={String(saved)}
                    sub={saved > 0 ? "in datasets/" : undefined} />
                  <StatCard label="Verworfen"  value={String(skipped)} />
                  <StatCard label="Fehler"     value={String(errors)} />
                </div>

                {Object.keys(reasonCounts).length > 0 && (
                  <div>
                    <p className="t-label mb-1.5">
                      Aufschlüsselung nach Grund
                    </p>
                    {Object.entries(reasonCounts).map(([reason, count]) => (
                      <div key={reason} className="flex items-center justify-between text-sm py-1.5 border-b border-line">
                        <span className="text-ink-2">{reasonLabel(reason)}</span>
                        <span className="font-mono text-xs text-ink">{count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── file list ────────────────────────────────────────── */}
            {displayQueue.length > 0 && (
              <div>
                <p className="t-label mb-1.5">Warteschlange</p>
                <div className="border-t border-line">
                  {displayQueue.map((item, i) => {
                    const r = item.result;
                    const displayName = r?.title
                      ? `${r.title}${r.artist ? ` — ${r.artist}` : ""}`
                      : item.name;

                    return (
                      <div
                        key={i}
                        className="flex items-center gap-3 py-1.5 border-b border-line"
                      >
                        {/* status indicator / play button */}
                        {item.status === "done" && r?.status === "saved" && r.song_id ? (
                          <PlayButton songId={r.song_id} />
                        ) : item.status === "processing" ? (
                          <div className="w-7 h-7 flex items-center justify-center shrink-0">
                            <span className="w-2 h-2 bg-signal animate-pulse" />
                          </div>
                        ) : (
                          <div className="w-7 h-7 flex items-center justify-center shrink-0">
                            <span className="w-1.5 h-1.5 bg-ink-4" />
                          </div>
                        )}

                        {/* name */}
                        <span className="flex-1 min-w-0 text-sm text-ink truncate">
                          {displayName}
                        </span>

                        {/* status */}
                        {item.status === "done" && r && (
                          <span className="flex items-center gap-1.5 font-mono text-2xs text-ink-2 shrink-0 max-w-[45%]">
                            <span className={`w-1.5 h-1.5 shrink-0 ${BADGE_DOT[r.status] ?? "bg-ink-4"}`} />
                            <span className="truncate">
                              {r.status === "saved"
                                ? "gespeichert"
                                : reasonLabel(r.reason)}
                            </span>
                          </span>
                        )}
                        {item.status === "pending" && !r && (
                          <span className="font-mono text-2xs text-ink-4 shrink-0">ausstehend</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </section>
        </div>

        {/* ── everything the backend is still working on, always last ── */}
        <PipelineList />

      </div>
    </div>
  );
}
