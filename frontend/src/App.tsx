import { useEffect, useRef, useState } from "react";
import { fetchNeighbors, fetchSongCount, fetchSongs } from "./services/api";
import type { Song } from "./types/song";
import { CardsPage } from "./components/CardsPage";
import { UmapView } from "./components/UmapView";
import { AnalysisPage } from "./components/analysis/AnalysisPage";
import { FilterPage } from "./components/filter/FilterPage";
import { PlayerBar } from "./components/PlayerBar";
import { UploadPage } from "./components/upload/UploadPage";
import { setNeighborSource, setQueue } from "./audio/player";

// The player stays free of API imports; the app wires the lookup in once.
setNeighborSource(fetchNeighbors);

type Tab = "cards" | "umap" | "analysis" | "filter" | "upload";

const POLL_INTERVAL_MS = 8_000;

export default function App() {
  const [songs, setSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("cards");
  const songsRef = useRef<Song[]>([]);

  const applySongs = (data: Song[]) => {
    songsRef.current = data;
    setSongs(data);
    setQueue(data.map((s) => s.id));
  };

  const refreshSongs = () =>
    fetchSongs()
      .then(applySongs)
      .catch(() => {});

  // Initial load
  useEffect(() => {
    fetchSongs()
      .then(applySongs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Poll for new songs while app is open (catches ingestion updates).
  // Only the cheap count endpoint is polled; the full list is refetched
  // when the count actually changed.
  useEffect(() => {
    if (loading) return;
    const id = setInterval(async () => {
      try {
        const count = await fetchSongCount();
        if (count !== songsRef.current.length) await refreshSongs();
      } catch {
        // backend temporarily unreachable — try again next tick
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [loading]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="h-screen flex flex-col bg-ground text-ink overflow-hidden">
      <header className="flex-shrink-0 h-11 border-b border-line flex items-stretch px-5">
        <h1 className="flex items-center pr-5 mr-2 border-r border-line text-[15px] font-bold leading-none stretch-expanded tracking-[-0.01em] whitespace-nowrap">
          Music Recommender
        </h1>
        <nav className="flex">
          {(["cards", "umap", "analysis", "filter", "upload"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              aria-current={tab === t ? "page" : undefined}
              className="tab"
            >
              {t === "cards" ? "Cards" : t === "umap" ? "UMAP" : t === "analysis" ? "Analysis" : t === "filter" ? "Filter" : "Upload"}
            </button>
          ))}
        </nav>
        {!loading && !error && (
          <p className="ml-auto self-center pl-4 font-mono text-2xs text-ink-3 whitespace-nowrap">
            <span className="text-ink">{songs.length}</span> songs
          </p>
        )}
      </header>

      <main className="flex-1 overflow-hidden">
        {loading && (
          <div className="h-full flex items-center justify-center font-mono text-xs text-ink-3">
            Loading songs…
          </div>
        )}
        {error && (
          <div className="h-full flex items-center justify-center font-mono text-xs text-bad">
            Error: {error}
          </div>
        )}
        {!loading && !error && (
          <>
            {tab === "cards" && <CardsPage songs={songs} />}
            {tab === "umap" && <UmapView songs={songs} />}
            {tab === "analysis" && <AnalysisPage songs={songs} />}
            {tab === "filter" && <FilterPage songs={songs} />}
            {tab === "upload" && <UploadPage />}
          </>
        )}
      </main>
      <PlayerBar songs={songs} />
    </div>
  );
}
