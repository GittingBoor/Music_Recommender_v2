import { useEffect, useRef, useState } from "react";
import {
  streamYoutubeSearch,
  searchYoutubePlaylists,
  enqueueYoutubeDownload,
  fetchYoutubeDownloads,
  fetchYoutubeExamples,
  fetchYoutubePlaylist,
  YoutubeRequestError,
} from "../../services/api";
import type {
  YoutubeSearchItem,
  YoutubePlaylistHit,
  YoutubeSearchEvent,
  YoutubeErrorDetail,
  UploadResult,
  YoutubeStage,
  YoutubeDownloadStatus,
} from "../../services/api";

interface Props {
  onDownloaded: (result: UploadResult) => void;
  onError: (detail: YoutubeErrorDetail | null) => void;
}

const STAGE_LABEL: Record<YoutubeStage, string> = {
  queued: "In Warteschlange",
  searching: "Sucht…",
  downloading: "Lädt herunter…",
  trimming: "Schneidet zu…",
  waiting: "Wartet auf Analyse",
  analyzing: "Analysiert…",
  done: "Fertig",
};

const DOWNLOAD_POLL_MS = 1_500;
const ELAPSED_TICK_MS = 500;
const MIN_VISIBLE_PROGRESS = 0.03;

/** A video handed to the backend queue that has not finished yet. */
interface ActiveDownload {
  readonly jobId: number;
  readonly title: string;
  readonly stage: YoutubeStage;
  readonly progress: number;
  readonly startedAt: number;
}

const EXAMPLE_COUNT = 5;
const VIDEO_RESULT_COUNT = 10;
const PLAYLIST_RESULT_COUNT = 3;

function formatDuration(seconds: number | null): string {
  if (!seconds) return "";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** A pasted playlist link is handled as a playlist, anything else as a search. */
function isPlaylistUrl(input: string): boolean {
  return /[?&]list=/.test(input);
}

function toDetail(err: unknown): YoutubeErrorDetail {
  if (err instanceof YoutubeRequestError) return err.detail;
  return {
    kind: "unknown",
    title: "Unerwarteter Fehler",
    explanation: "Im Browser ist etwas schiefgelaufen, bevor der Server antworten konnte.",
    scope: "global",
    raw_message: err instanceof Error ? err.message : String(err),
  };
}

export function YoutubeSearch({ onDownloaded, onError }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<YoutubeSearchItem[]>([]);
  const [listTitle, setListTitle] = useState<string | null>(null);
  const [playlists, setPlaylists] = useState<YoutubePlaylistHit[]>([]);
  const [searching, setSearching] = useState(false);
  // Videos that became part of the library during this session.
  const [addedIds, setAddedIds] = useState<ReadonlySet<string>>(new Set());
  // Bumped per search/playlist load so events from an older stream are ignored.
  const searchToken = useRef(0);

  // Examples are only a starting point — they disappear on the first search.
  const [examples, setExamples] = useState<YoutubeSearchItem[]>([]);
  const [loadingExamples, setLoadingExamples] = useState(true);
  const [showExamples, setShowExamples] = useState(true);

  // Queued and running downloads by video id; any number can run at once.
  const [active, setActive] = useState<ReadonlyMap<string, ActiveDownload>>(new Map());
  const activeRef = useRef(active);
  activeRef.current = active;
  const pollingRef = useRef(false);
  const [now, setNow] = useState(() => Date.now());
  const hasActive = active.size > 0;

  useEffect(() => {
    if (!hasActive) return;
    const poll = window.setInterval(() => { void pollDownloads(); }, DOWNLOAD_POLL_MS);
    const tick = window.setInterval(() => setNow(Date.now()), ELAPSED_TICK_MS);
    return () => { clearInterval(poll); clearInterval(tick); };
    // pollDownloads reads the latest downloads through activeRef.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasActive]);

  useEffect(() => {
    let cancelled = false;
    setLoadingExamples(true);
    fetchYoutubeExamples(EXAMPLE_COUNT)
      .then((items) => { if (!cancelled) setExamples(items); })
      .catch((err) => { if (!cancelled) onError(toDetail(err)); })
      .finally(() => { if (!cancelled) setLoadingExamples(false); });
    return () => { cancelled = true; };
    // Runs once when the Upload tab opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const input = query.trim();
    if (!input || searching) return;

    setSearching(true);
    onError(null);
    setShowExamples(false);
    setListTitle(null);
    setPlaylists([]);
    const token = ++searchToken.current;
    const isCurrent = () => token === searchToken.current;
    try {
      if (isPlaylistUrl(input)) {
        await openPlaylist(input);
      } else {
        setResults([]);
        const playlistSearch = searchYoutubePlaylists(input, PLAYLIST_RESULT_COUNT)
          .then((hits) => { if (isCurrent()) setPlaylists(hits); })
          .catch((err: unknown) => { if (isCurrent()) onError(toDetail(err)); });
        await streamYoutubeSearch(input, VIDEO_RESULT_COUNT, (event) => {
          if (isCurrent()) applySearchEvent(event);
        });
        await playlistSearch;
      }
    } catch (err: unknown) {
      if (isCurrent()) {
        onError(toDetail(err));
        setResults([]);
      }
    } finally {
      if (isCurrent()) setSearching(false);
    }
  }

  function applySearchEvent(event: YoutubeSearchEvent) {
    switch (event.type) {
      case "results":
        setResults(event.items);
        // Hits are usable now; the category checks keep running in the background.
        setSearching(false);
        break;
      case "rejected":
        setResults((prev) => prev.filter((item) => item.video_id !== event.video_id));
        break;
      case "done":
        break;
    }
  }

  async function openPlaylist(url: string) {
    const playlist = await fetchYoutubePlaylist(url);
    setListTitle(playlist.title);
    setResults(playlist.items);
    setPlaylists([]);
  }

  async function onOpenPlaylist(hit: YoutubePlaylistHit) {
    if (searching) return;
    const token = ++searchToken.current;
    setSearching(true);
    onError(null);
    try {
      await openPlaylist(hit.url);
    } catch (err: unknown) {
      onError(toDetail(err));
    } finally {
      if (token === searchToken.current) setSearching(false);
    }
  }

  function isInLibrary(item: YoutubeSearchItem): boolean {
    return item.in_library || addedIds.has(item.video_id);
  }

  async function startDownload(item: YoutubeSearchItem) {
    if (activeRef.current.has(item.video_id)) return;
    try {
      const jobId = await enqueueYoutubeDownload(item);
      setActive((prev) => new Map(prev).set(item.video_id, {
        jobId, title: item.title, stage: "queued", progress: 0, startedAt: Date.now(),
      }));
    } catch (err: unknown) {
      reportFailure(item.title, toDetail(err));
    }
  }

  async function pollDownloads() {
    const entries = [...activeRef.current];
    if (entries.length === 0 || pollingRef.current) return;
    pollingRef.current = true;
    try {
      const statuses = await fetchYoutubeDownloads(entries.map(([, d]) => d.jobId));
      const byJob = new Map(statuses.map((st) => [st.job_id, st]));
      for (const [videoId, download] of entries) {
        const status = byJob.get(download.jobId);
        if (status) applyStatus(videoId, download, status);
      }
    } catch {
      // A dropped poll is retried on the next tick; the jobs keep running on the server.
    } finally {
      pollingRef.current = false;
    }
  }

  function applyStatus(videoId: string, download: ActiveDownload, status: YoutubeDownloadStatus) {
    if (!status.result) {
      setActive((prev) => new Map(prev).set(videoId, {
        ...download, stage: status.stage, progress: status.progress,
      }));
      return;
    }
    const result: UploadResult = { ...status.result, filename: status.result.filename || download.title };
    setActive((prev) => {
      const next = new Map(prev);
      next.delete(videoId);
      return next;
    });
    if (result.status === "error" && result.error) onError(result.error);
    if (result.status === "saved" || result.reason === "duplicate") {
      setAddedIds((prev) => new Set(prev).add(videoId));
    }
    onDownloaded(result);
  }

  function reportFailure(title: string, detail: YoutubeErrorDetail) {
    onError(detail);
    onDownloaded({
      status: "error",
      reason: detail.title,
      title,
      artist: null,
      song_id: null,
      filename: title,
      error: detail,
    });
  }

  async function onDownloadAll() {
    onError(null);
    const pending = results.filter((item) => !isInLibrary(item) && !active.has(item.video_id));
    for (const item of pending) await startDownload(item);
  }

  const knownCount = results.filter(isInLibrary).length;
  const runningCount = results.filter((item) => active.has(item.video_id)).length;
  const downloadableCount = results.length - knownCount - runningCount;
  // A search over-fetches so rejected hits can be backfilled; a playlist shows everything.
  const shownResults = listTitle ? results : results.slice(0, VIDEO_RESULT_COUNT);
  const visible = showExamples && results.length === 0 ? examples : shownResults;
  const showingExamples = showExamples && results.length === 0 && examples.length > 0;

  return (
    <div className="space-y-4">
      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Song suchen oder Playlist-Link einfügen…"
          className="field flex-1 h-9"
        />
        <button
          type="submit"
          disabled={searching || !query.trim()}
          className="btn btn-primary h-9 px-4 text-sm"
        >
          {searching ? "Sucht…" : isPlaylistUrl(query) ? "Playlist laden" : "Suchen"}
        </button>
      </form>

      <p className="text-xs text-ink-3 leading-relaxed max-w-2xl">
        Angezeigt werden Videos zwischen 45 Sekunden und 10 Minuten, keine Livestreams
        und keine Mixes. Treffer, die YouTube nicht als Musik führt, verschwinden nach
        der Prüfung wieder.
      </p>

      {/* ── heading above the list ─────────────────────────────────── */}
      {showingExamples && !loadingExamples && (
        <div className="flex items-center justify-between gap-4 pt-2">
          <p className="t-label min-w-0">
            Vorschläge — noch nicht in der Bibliothek
          </p>
          <button
            onClick={() => {
              setLoadingExamples(true);
              onError(null);
              fetchYoutubeExamples(EXAMPLE_COUNT)
                .then(setExamples)
                .catch((err) => onError(toDetail(err)))
                .finally(() => setLoadingExamples(false));
            }}
            disabled={loadingExamples}
            className="btn-quiet shrink-0"
          >
            Andere zeigen
          </button>
        </div>
      )}

      {loadingExamples && showExamples && results.length === 0 && (
        <p className="font-mono text-2xs text-ink-3 animate-pulse pt-2">Sucht Vorschläge…</p>
      )}

      {listTitle && (
        <div className="flex items-center justify-between gap-4 pt-2">
          <p className="t-label truncate">
            Playlist: <span className="text-ink">{listTitle}</span> · {results.length} Songs
            {knownCount > 0 && ` · ${knownCount} bereits vorhanden`}
          </p>
          <button
            onClick={() => { void onDownloadAll(); }}
            disabled={downloadableCount === 0}
            className="btn btn-primary shrink-0"
          >
            {runningCount > 0 && downloadableCount === 0 ? `${runningCount} in Arbeit` : "Alle herunterladen"}
          </button>
        </div>
      )}

      {/* ── result list ────────────────────────────────────────────── */}
      {visible.length > 0 && (
        <div className="border-t border-line">
          {visible.map((item) => {
            const download = active.get(item.video_id);
            return (
              <div
                key={item.video_id}
                className="flex items-center gap-3 py-2 border-b border-line"
              >
                {item.thumbnail ? (
                  <img
                    src={item.thumbnail}
                    alt=""
                    className="w-16 h-9 object-cover shrink-0 bg-raised"
                  />
                ) : (
                  <div className="w-16 h-9 shrink-0 bg-raised" />
                )}

                <div className="flex-1 min-w-0">
                  <p className="text-sm text-ink truncate">{item.title}</p>
                  <p className="text-xs text-ink-3 truncate">
                    {item.uploader ?? "Unbekannt"}
                    {item.duration ? <span className="font-mono text-2xs"> · {formatDuration(item.duration)}</span> : ""}
                  </p>
                </div>

                {download ? (
                  <div className="w-28 md:w-44 shrink-0">
                    <div className="flex justify-between gap-2 text-xs text-ink-2 mb-1.5">
                      <span className="truncate">{STAGE_LABEL[download.stage]}</span>
                      <span className="font-mono text-2xs text-ink-3 tabular-nums shrink-0">
                        {Math.max(0, (now - download.startedAt) / 1000).toFixed(0)}s
                      </span>
                    </div>
                    <div className="h-[2px] bg-line">
                      <div
                        className={`h-full transition-all duration-500 ${download.stage === "queued" ? "bg-ink-4" : "bg-signal"}`}
                        style={{ width: `${Math.max(download.progress, MIN_VISIBLE_PROGRESS) * 100}%` }}
                      />
                    </div>
                  </div>
                ) : isInLibrary(item) ? (
                  <span className="flex items-center gap-1.5 font-mono text-2xs text-ink-2 shrink-0">
                    <span className="w-1.5 h-1.5 bg-ok" />
                    Bereits vorhanden
                  </span>
                ) : (
                  <button
                    onClick={() => { void startDownload(item); }}
                    className="btn"
                  >
                    Download
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── playlists found by the search ──────────────────────────── */}
      {/* Held back until the songs are in, so playlists always sit below them. */}
      {playlists.length > 0 && !searching && (
        <div>
          <p className="t-label pt-4 pb-1.5 border-b border-line">
            Playlists
          </p>
          {playlists.map((hit) => (
            <div
              key={hit.playlist_id}
              className="flex items-center gap-3 py-2 border-b border-line"
            >
              {hit.thumbnail ? (
                <img
                  src={hit.thumbnail}
                  alt=""
                  className="w-16 h-9 object-cover shrink-0 bg-raised"
                />
              ) : (
                <div className="w-16 h-9 shrink-0 bg-raised" />
              )}

              <div className="flex-1 min-w-0">
                <p className="text-sm text-ink truncate">{hit.title}</p>
                <p className="text-xs text-ink-3 truncate">
                  Playlist · {hit.uploader ?? "Unbekannt"}
                </p>
              </div>

              <button
                onClick={() => onOpenPlaylist(hit)}
                disabled={searching}
                className="btn"
              >
                Öffnen
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
