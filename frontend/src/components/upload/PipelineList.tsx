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

const STAGE_CLASS: Record<PipelineStage, string> = {
  analyzing:   "bg-violet-500/15 text-violet-300 border-violet-500/40",
  trimming:    "bg-sky-500/15 text-sky-300 border-sky-500/40",
  downloading: "bg-sky-500/15 text-sky-300 border-sky-500/40",
  searching:   "bg-sky-500/15 text-sky-300 border-sky-500/40",
  waiting:     "bg-gray-800 text-gray-400 border-gray-700",
  queued:      "bg-gray-900 text-gray-500 border-gray-800",
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
    <section className="space-y-2 pt-2">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
          In der Pipeline
        </h2>
        {jobs && jobs.length > 0 && (
          <span className="text-xs text-gray-500">
            {active} aktiv · {queued} wartend
          </span>
        )}
      </div>

      {failed && jobs === null && (
        <p className="text-xs text-red-400">Pipeline-Status nicht erreichbar.</p>
      )}
      {jobs && jobs.length === 0 && (
        <p className="text-xs text-gray-600">Gerade wird nichts heruntergeladen oder analysiert.</p>
      )}

      {jobs && jobs.length > 0 && (
        <div className="space-y-1">
          {jobs.slice(0, MAX_ROWS).map((job) => (
            <div
              key={job.id}
              className="flex items-center gap-3 px-3 py-2 rounded-lg bg-gray-900 border border-gray-800"
            >
              <span className="w-7 h-7 flex items-center justify-center shrink-0">
                {job.stage === "queued" || job.stage === "waiting" ? (
                  <span className="w-2.5 h-2.5 rounded-full bg-gray-700" />
                ) : (
                  <span className="w-3 h-3 rounded-full bg-violet-500 animate-pulse" />
                )}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-300 truncate">{job.label}</p>
                <p className="text-[11px] text-gray-600">
                  {SOURCE_LABEL[job.source] ?? job.source}
                  {job.stage !== "queued" && ` · seit ${fmtSeconds(job.seconds_in_stage)}`}
                </p>
              </div>
              <span className={`shrink-0 text-[11px] px-2 py-0.5 rounded border whitespace-nowrap ${STAGE_CLASS[job.stage]}`}>
                {STAGE_LABEL[job.stage]}
              </span>
            </div>
          ))}
          {jobs.length > MAX_ROWS && (
            <p className="text-xs text-gray-600 text-center pt-1">
              … und {jobs.length - MAX_ROWS} weitere in der Warteschlange
            </p>
          )}
        </div>
      )}
    </section>
  );
}
