import { useEffect, useState } from "react";
import type { DownloadProgress } from "../services/api";

// The server needs a few seconds before the first byte; that wait fills the
// first part of the bar, creeping on with time, the download the rest.
const WAIT_SHARE = 0.3;
const WAIT_TIME_CONSTANT_MS = 4000;
const BYTES_PER_MB = 1024 * 1024;

function useElapsedMs(running: boolean): number {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!running) return;
    const start = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      setElapsed(now - start);
      frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [running]);
  return elapsed;
}

/** 0–1, or null when the size is unknown (the bar then sweeps). */
function shareDone(progress: DownloadProgress | null, waitedMs: number): number | null {
  if (!progress) return WAIT_SHARE * (1 - Math.exp(-waitedMs / WAIT_TIME_CONSTANT_MS));
  if (!progress.total) return null;
  return WAIT_SHARE + (1 - WAIT_SHARE) * Math.min(1, progress.loaded / progress.total);
}

function megabytes(bytes: number): string {
  return (bytes / BYTES_PER_MB).toFixed(1);
}

/** Full-page loading state while the song list, which every page needs, comes in. */
export function LoadingBar({ progress }: { readonly progress: DownloadProgress | null }) {
  const waitedMs = useElapsedMs(progress === null);
  const share = shareDone(progress, waitedMs);
  const percent = share == null ? null : Math.round(share * 100);
  const detail = progress
    ? `${megabytes(progress.loaded)}${progress.total ? ` / ${megabytes(progress.total)}` : ""} MB`
    : "Preparing library…";

  return (
    <div className="h-full flex items-center justify-center px-6">
      <div className="w-full max-w-xs">
        <div className="flex items-baseline justify-between gap-3 mb-2">
          <span className="text-sm text-ink">Loading songs</span>
          <span className="font-mono text-2xs text-ink-3 tabular-nums">{percent == null ? "" : `${percent}%`}</span>
        </div>
        <div
          className="relative h-[3px] overflow-hidden bg-line-strong"
          role="progressbar"
          aria-label="Loading songs"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent ?? undefined}
        >
          {share == null ? (
            <div className="loading-sweep absolute inset-y-0 w-1/3 bg-signal" />
          ) : (
            <div className="h-full bg-signal transition-[width] duration-200 ease-out" style={{ width: `${share * 100}%` }} />
          )}
        </div>
        <p className="mt-2 font-mono text-2xs text-ink-3 tabular-nums">{detail}</p>
      </div>
    </div>
  );
}
