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
    // 100dvh instead of 100vh: on phones 100vh ignores the browser toolbar,
    // which would push the player bar below the visible area.
    <div className="h-screen h-[100dvh] flex flex-col bg-gray-950 text-white overflow-hidden">
      <header className="flex-shrink-0 border-b border-gray-800 px-3 pt-2 pb-1.5 md:px-6 md:py-3 flex flex-col md:flex-row md:items-center gap-1.5 md:gap-6">
        <div className="min-w-0 flex items-baseline gap-2 md:block px-1 md:px-0">
          <h1 className="text-base md:text-lg font-bold tracking-tight leading-none whitespace-nowrap">
            Music Recommender
          </h1>
          {!loading && !error && (
            <p className="text-xs text-gray-500 md:mt-0.5 whitespace-nowrap">{songs.length} songs</p>
          )}
        </div>
        <nav className="grid grid-cols-5 gap-1 md:flex">
          {(["cards", "umap", "analysis", "filter", "upload"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-1 md:px-3 py-2 md:py-1.5 rounded text-[13px] md:text-sm font-medium transition-colors ${
                tab === t
                  ? "bg-gray-800 text-white"
                  : "text-gray-500 hover:text-gray-300 hover:bg-gray-900"
              }`}
            >
              {t === "cards" ? "Cards" : t === "umap" ? "UMAP" : t === "analysis" ? "Analysis" : t === "filter" ? "Filter" : "Upload"}
            </button>
          ))}
        </nav>
      </header>

      <main className="flex-1 overflow-hidden">
        {loading && (
          <div className="h-full flex items-center justify-center text-gray-500 text-sm">
            Loading songs…
          </div>
        )}
        {error && (
          <div className="h-full flex items-center justify-center text-red-400 text-sm">
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
