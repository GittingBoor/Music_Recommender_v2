import { useRef, useState } from "react";
import { uploadSong } from "../../services/api";
import type { UploadResult } from "../../services/api";
import { PlayButton } from "../PlayButton";
import { StatCard } from "../StatCard";

// ── types ─────────────────────────────────────────────────────────────────
type ItemStatus = "pending" | "processing" | "done";

interface QueueItem {
  file: File;
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
  duplicate:            "Duplikat",
  no_acoustid_match:    "Kein AcoustID-Treffer",
  too_long_unrecognized:"Zu lang (unbekannt)",
  unsupported_format:   "Format nicht unterstützt",
  error:                "Fehler",
};

function reasonLabel(reason: string | null): string {
  if (!reason) return "";
  return REASON_LABEL[reason] ?? reason;
}

const BADGE_CLASS: Record<string, string> = {
  saved:   "bg-emerald-900 text-emerald-300",
  skipped: "bg-yellow-900/60 text-yellow-300",
  error:   "bg-red-900/60 text-red-300",
};

// ── component ─────────────────────────────────────────────────────────────
export function UploadPage() {
  const [queue, setQueue]     = useState<QueueItem[]>([]);
  const [running, setRunning] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── add files ────────────────────────────────────────────────────────
  function addFiles(files: FileList | File[]) {
    const arr = Array.from(files);
    const items: QueueItem[] = arr.map((file) => ({
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

      // Already resolved client-side (unsupported format)
      if (item.result) continue;

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
          filename: item.file.name,
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
      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">

        {/* ── drop zone ────────────────────────────────────────────── */}
        <div
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => !running && inputRef.current?.click()}
          className={`
            border-2 border-dashed rounded-xl px-8 py-14 flex flex-col items-center
            gap-3 cursor-pointer select-none transition-colors
            ${dragOver
              ? "border-violet-500 bg-violet-950/30"
              : "border-gray-700 bg-gray-900/40 hover:border-gray-600 hover:bg-gray-900/60"}
            ${running ? "pointer-events-none opacity-60" : ""}
          `}
        >
          <svg
            className={`w-10 h-10 ${dragOver ? "text-violet-400" : "text-gray-600"} transition-colors`}
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}
          >
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
          </svg>
          <p className="text-sm text-gray-400 text-center">
            MP3-Dateien hier ablegen oder klicken zum Auswählen
          </p>
          <p className="text-xs text-gray-600">
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

        {/* ── action bar ───────────────────────────────────────────── */}
        {queue.length > 0 && (
          <div className="flex items-center gap-3">
            {!running && !allDone && (
              <button
                onClick={() => processQueue(displayQueue)}
                className="px-4 py-1.5 rounded bg-violet-600 hover:bg-violet-500 text-sm font-medium text-white transition-colors"
              >
                {queue.filter((q) => !q.result).length} Dateien verarbeiten
              </button>
            )}
            {running && (
              <span className="text-sm text-gray-400 animate-pulse">
                Verarbeite…
              </span>
            )}
            <button
              onClick={() => { setQueue([]); setRunning(false); }}
              disabled={running}
              className="px-4 py-1.5 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-sm font-medium text-gray-300 transition-colors"
            >
              Zurücksetzen
            </button>
          </div>
        )}

        {/* ── progress bar ─────────────────────────────────────────── */}
        {queue.length > 0 && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-gray-500">
              <span>{doneCount} / {totalCount} erledigt</span>
              {allDone && <span className="text-emerald-400">Fertig</span>}
            </div>
            <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-violet-500 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {/* ── statistics (shown once all done) ─────────────────────── */}
        {allDone && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <StatCard label="Gesamt"     value={String(totalCount)} />
              <StatCard label="Gespeichert" value={String(saved)}
                sub={saved > 0 ? "in datasets/" : undefined} />
              <StatCard label="Verworfen"  value={String(skipped)} />
              <StatCard label="Fehler"     value={String(errors)} />
            </div>

            {Object.keys(reasonCounts).length > 0 && (
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2">
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">
                  Aufschlüsselung nach Grund
                </p>
                {Object.entries(reasonCounts).map(([reason, count]) => (
                  <div key={reason} className="flex items-center justify-between text-sm">
                    <span className="text-gray-400">{reasonLabel(reason)}</span>
                    <span className="font-mono text-gray-300">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── file list ────────────────────────────────────────────── */}
        {displayQueue.length > 0 && (
          <div className="space-y-1">
            {displayQueue.map((item, i) => {
              const r = item.result;
              const displayName = r?.title
                ? `${r.title}${r.artist ? ` — ${r.artist}` : ""}`
                : item.file.name;

              return (
                <div
                  key={i}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg bg-gray-900 border border-gray-800"
                >
                  {/* status indicator / play button */}
                  {item.status === "done" && r?.status === "saved" && r.song_id ? (
                    <PlayButton songId={r.song_id} />
                  ) : item.status === "processing" ? (
                    <div className="w-7 h-7 flex items-center justify-center shrink-0">
                      <span className="w-3 h-3 rounded-full bg-violet-500 animate-pulse" />
                    </div>
                  ) : (
                    <div className="w-7 h-7 flex items-center justify-center shrink-0">
                      <span className="w-2.5 h-2.5 rounded-full bg-gray-700" />
                    </div>
                  )}

                  {/* name */}
                  <span className="flex-1 min-w-0 text-sm text-gray-300 truncate">
                    {displayName}
                  </span>

                  {/* badge */}
                  {item.status === "done" && r && (
                    <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 font-medium ${BADGE_CLASS[r.status] ?? ""}`}>
                      {r.status === "saved"
                        ? "gespeichert"
                        : reasonLabel(r.reason)}
                    </span>
                  )}
                  {item.status === "pending" && !r && (
                    <span className="text-xs text-gray-600 shrink-0">ausstehend</span>
                  )}
                </div>
              );
            })}
          </div>
        )}

      </div>
    </div>
  );
}
