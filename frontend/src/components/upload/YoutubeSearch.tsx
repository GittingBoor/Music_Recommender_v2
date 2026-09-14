import { useEffect, useRef, useState } from "react";
import {
  streamYoutubeSearch,
  searchYoutubePlaylists,
  downloadYoutube,
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
} from "../../services/api";

interface Props {
  onDownloaded: (result: UploadResult) => void;
  onError: (detail: YoutubeErrorDetail | null) => void;
}

const STAGE_LABEL: Record<YoutubeStage, string> = {
  downloading: "Lädt herunter…",
  trimming: "Schneidet zu…",
  analyzing: "Analysiert…",
  done: "Fertig",
};

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

  // active download state (only one at a time)
  const [downloading, setDownloading] = useState<string | null>(null);
  const [stage, setStage] = useState<YoutubeStage>("downloading");
  const [progress, setProgress] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [batchLeft, setBatchLeft] = useState(0);
  const timerRef = useRef<number | null>(null);

  useEffect(() => () => stopTimer(), []);

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

  async function runDownload(item: YoutubeSearchItem) {
    setDownloading(item.video_id);
    setStage("downloading");
    setProgress(0);
    startTimer();
    try {
      const result = await downloadYoutube(item.video_id, item.title, (p) => {
        setStage(p.stage);
        setProgress(p.progress);
      });
      if (result.status === "error" && result.error) onError(result.error);
      if (result.status === "saved" || result.reason === "duplicate") {
        setAddedIds((prev) => new Set(prev).add(item.video_id));
      }
      onDownloaded(result);
    } catch (err: unknown) {
      const detail = toDetail(err);
      onError(detail);
      onDownloaded({
        status: "error",
        reason: detail.title,
        title: item.title,
        artist: null,
        song_id: null,
        filename: item.title,
        error: detail,
      });
    } finally {
      stopTimer();
      setDownloading(null);
    }
  }

  async function onDownloadAll() {
    onError(null);
    const pending = results.filter((item) => !isInLibrary(item));
    for (let i = 0; i < pending.length; i++) {
      setBatchLeft(pending.length - i);
      await runDownload(pending[i]);
    }
    setBatchLeft(0);
  }

  const busy = downloading !== null;
  const knownCount = results.filter(isInLibrary).length;
  // A search over-fetches so rejected hits can be backfilled; a playlist shows everything.
  const shownResults = listTitle ? results : results.slice(0, VIDEO_RESULT_COUNT);
  const visible = showExamples && results.length === 0 ? examples : shownResults;
  const showingExamples = showExamples && results.length === 0 && examples.length > 0;

  return (
    <div className="space-y-3">
      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Song suchen oder Playlist-Link einfügen…"
          className="flex-1 px-3 py-2 rounded-lg bg-gray-900 border border-gray-800 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-violet-600"
        />
        <button
          type="submit"
          disabled={searching || !query.trim()}
          className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-sm font-medium text-white transition-colors"
        >
          {searching ? "Sucht…" : isPlaylistUrl(query) ? "Playlist laden" : "Suchen"}
        </button>
      </form>

      <p className="text-xs text-gray-600">
        Angezeigt werden Videos zwischen 45 Sekunden und 10 Minuten, keine Livestreams
        und keine Mixes. Treffer, die YouTube nicht als Musik führt, verschwinden nach
        der Prüfung wieder.
      </p>

      {/* ── heading above the list ─────────────────────────────────── */}
      {showingExamples && !loadingExamples && (
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
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
            disabled={busy || loadingExamples}
            className="text-xs text-violet-400 hover:text-violet-300 disabled:opacity-40 transition-colors"
          >
            Andere zeigen
          </button>
        </div>
      )}

      {loadingExamples && showExamples && results.length === 0 && (
        <p className="text-xs text-gray-600 animate-pulse">Sucht Vorschläge…</p>
      )}

      {listTitle && (
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider truncate">
            Playlist: {listTitle} · {results.length} Songs
            {knownCount > 0 && ` · ${knownCount} bereits vorhanden`}
          </p>
          <button
            onClick={onDownloadAll}
            disabled={busy || results.length === knownCount}
            className="px-3 py-1 rounded bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-xs font-medium text-white transition-colors shrink-0"
          >
            {batchLeft > 0 ? `Lädt… (${batchLeft} übrig)` : "Alle herunterladen"}
          </button>
        </div>
      )}

      {/* ── result list ────────────────────────────────────────────── */}
      {visible.length > 0 && (
        <div className="space-y-1">
          {visible.map((item) => {
            const isDownloading = downloading === item.video_id;
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
                ) : isInLibrary(item) ? (
                  <span className="px-3 py-1.5 rounded bg-emerald-900/40 text-xs font-medium text-emerald-300 shrink-0">
                    Bereits vorhanden
                  </span>
                ) : (
                  <button
                    onClick={() => runDownload(item)}
                    disabled={busy}
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

      {/* ── playlists found by the search ──────────────────────────── */}
      {/* Held back until the songs are in, so playlists always sit below them. */}
      {playlists.length > 0 && !searching && (
        <div className="space-y-1">
          <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider pt-2">
            Playlists
          </p>
          {playlists.map((hit) => (
            <div
              key={hit.playlist_id}
              className="flex items-center gap-3 px-3 py-2 rounded-lg bg-gray-900 border border-gray-800"
            >
              {hit.thumbnail ? (
                <img
                  src={hit.thumbnail}
                  alt=""
                  className="w-16 h-9 object-cover rounded shrink-0 bg-gray-800"
                />
              ) : (
                <div className="w-16 h-9 rounded shrink-0 bg-gray-800" />
              )}

              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-200 truncate">{hit.title}</p>
                <p className="text-xs text-gray-500 truncate">
                  Playlist · {hit.uploader ?? "Unbekannt"}
                </p>
              </div>

              <button
                onClick={() => onOpenPlaylist(hit)}
                disabled={busy || searching}
                className="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-xs font-medium text-gray-200 transition-colors shrink-0"
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
