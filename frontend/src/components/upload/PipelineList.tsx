import { useEffect, useState } from "react";
import { fetchPipeline } from "../../services/api";
import type { PipelineJob, PipelineStage } from "../../services/api";

const POLL_MS = 3_000;
// The bulk queue can hold hundreds of songs; the rest is summarised.
const MAX_ROWS = 100;

const STAGE_LABEL: Record<PipelineStage, string> = {
  analyzing:   "Analysiert",
  trimming:    "Schneidet zu",
  downloading: "Lädt herunter",
  searching:   "Sucht auf YouTube",
  waiting:     "Wartet auf Analyse",
  queued:      "In der Warteschlange",
};

// Signal marks the one song being analysed; everything else stays quiet.
const STAGE_CLASS: Record<PipelineStage, string> = {
  analyzing:   "text-signal",
  trimming:    "text-ink-2",
  downloading: "text-ink-2",
  searching:   "text-ink-2",
  waiting:     "text-ink-3",
  queued:      "text-ink-4",
};

const SOURCE_LABEL: Record<string, string> = {
  upload:  "Upload",
  youtube: "YouTube",
  bulk:    "Liste",
};

function fmtSeconds(s: number): string {
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}:${String(s % 60).padStart(2, "0")} min` : `${s}s`;
}

/** Live list of every song the backend is still downloading or analysing. */
export function PipelineList() {
  const [jobs, setJobs] = useState<PipelineJob[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetchPipeline()
        .then((j) => { if (!cancelled) { setJobs(j); setFailed(false); } })
        .catch(() => { if (!cancelled) setFailed(true); });
    load();
    const id = setInterval(load, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const active = jobs?.filter((j) => j.stage !== "queued").length ?? 0;
  const queued = (jobs?.length ?? 0) - active;

  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="t-section">In der Pipeline</h2>
        {jobs && jobs.length > 0 && (
          <span className="font-mono text-2xs text-ink-3 tabular-nums">
            {active} aktiv · {queued} wartend
          </span>
        )}
      </div>

      {failed && jobs === null && (
        <p className="font-mono text-xs text-bad">Pipeline-Status nicht erreichbar.</p>
      )}
      {jobs && jobs.length === 0 && (
        <p className="font-mono text-xs text-ink-4">Gerade wird nichts heruntergeladen oder analysiert.</p>
      )}

      {jobs && jobs.length > 0 && (
        <div className="border-t border-line">
          {jobs.slice(0, MAX_ROWS).map((job) => (
            <div
              key={job.id}
              className="flex items-center gap-3 py-1.5 border-b border-line"
            >
              <span className="w-7 h-7 flex items-center justify-center shrink-0">
                {job.stage === "queued" || job.stage === "waiting" ? (
                  <span className="w-1.5 h-1.5 bg-ink-4" />
                ) : (
                  <span className="w-2 h-2 bg-signal animate-pulse" />
                )}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-ink truncate">{job.label}</p>
                <p className="font-mono text-2xs text-ink-3">
                  {SOURCE_LABEL[job.source] ?? job.source}
                  {job.stage !== "queued" && ` · seit ${fmtSeconds(job.seconds_in_stage)}`}
                </p>
              </div>
              <span className={`shrink-0 font-mono text-2xs whitespace-nowrap ${STAGE_CLASS[job.stage]}`}>
                {STAGE_LABEL[job.stage]}
              </span>
            </div>
          ))}
          {jobs.length > MAX_ROWS && (
            <p className="font-mono text-2xs text-ink-4 pt-2">
              … und {jobs.length - MAX_ROWS} weitere in der Warteschlange
            </p>
          )}
        </div>
      )}
    </section>
  );
}
