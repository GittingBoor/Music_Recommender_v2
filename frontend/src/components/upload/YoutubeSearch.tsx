import { useEffect, useRef, useState } from "react";
import { searchYoutube, downloadYoutube } from "../../services/api";
import type {
  YoutubeSearchItem,
  UploadResult,
  YoutubeStage,
} from "../../services/api";

interface Props {
  onDownloaded: (result: UploadResult) => void;
}

const STAGE_LABEL: Record<YoutubeStage, string> = {
  downloading: "Lädt herunter…",
  trimming: "Schneidet zu…",
  analyzing: "Analysiert…",
  done: "Fertig",
};

function formatDuration(seconds: number | null): string {
  if (!seconds) return "";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function YoutubeSearch({ onDownloaded }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<YoutubeSearchItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // active download state (only one at a time)
  const [downloading, setDownloading] = useState<string | null>(null);
  const [stage, setStage] = useState<YoutubeStage>("downloading");
  const [progress, setProgress] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<number | null>(null);

  useEffect(() => () => stopTimer(), []);

  function startTimer() {
    setElapsed(0);
    const start = performance.now();
    timerRef.current = window.setInterval(() => {
      setElapsed((performance.now() - start) / 1000);
    }, 100);
  }

  function stopTimer() {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim() || searching) return;
    setSearching(true);
    setError(null);
    try {
      setResults(await searchYoutube(query.trim()));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  async function onDownload(item: YoutubeSearchItem) {
    setDownloading(item.video_id);
    setStage("downloading");
    setProgress(0);
    startTimer();
    try {
      const result = await downloadYoutube(item.video_id, item.title, (p) => {
        setStage(p.stage);
        setProgress(p.progress);
      });
      onDownloaded(result);
    } catch (err: unknown) {
      onDownloaded({
        status: "error",
        reason: err instanceof Error ? err.message : String(err),
        title: item.title,
        artist: null,
        song_id: null,
        filename: item.title,
      });
    } finally {
      stopTimer();
      setDownloading(null);
    }
  }

  return (
    <div className="space-y-3">
      <form onSubmit={onSearch} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="YouTube durchsuchen…"
          className="flex-1 px-3 py-2 rounded-lg bg-gray-900 border border-gray-800 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-violet-600"
        />
        <button
          type="submit"
          disabled={searching || !query.trim()}
          className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-sm font-medium text-white transition-colors"
        >
          {searching ? "Suche…" : "Suchen"}
        </button>
      </form>

      {error && (
        <p className="text-xs text-red-400">YouTube-Suche fehlgeschlagen: {error}</p>
      )}

      {results.length > 0 && (
        <div className="space-y-1">
          {results.map((item) => {
            const isDownloading = downloading === item.video_id;
            const disabled = downloading !== null;
            return (
              <div
                key={item.video_id}
                className="flex items-center gap-3 px-3 py-2 rounded-lg bg-gray-900 border border-gray-800"
              >
                {item.thumbnail ? (
                  <img
                    src={item.thumbnail}
                    alt=""
                    className="w-16 h-9 object-cover rounded shrink-0 bg-gray-800"
                  />
                ) : (
                  <div className="w-16 h-9 rounded shrink-0 bg-gray-800" />
                )}

                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-200 truncate">{item.title}</p>
                  <p className="text-xs text-gray-500 truncate">
                    {item.uploader ?? "Unbekannt"}
                    {item.duration ? ` · ${formatDuration(item.duration)}` : ""}
                  </p>
                </div>

                {isDownloading ? (
                  <div className="w-44 shrink-0">
                    <div className="flex justify-between text-xs text-gray-400 mb-1">
                      <span>{STAGE_LABEL[stage]}</span>
                      <span className="font-mono">{elapsed.toFixed(1)}s</span>
                    </div>
                    <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-violet-500 transition-all duration-500"
                        style={{ width: `${progress * 100}%` }}
                      />
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => onDownload(item)}
                    disabled={disabled}
                    className="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-xs font-medium text-gray-200 transition-colors shrink-0"
                  >
                    Download
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
