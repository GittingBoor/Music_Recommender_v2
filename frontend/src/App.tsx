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
    // Phones: title and song count on the first row, the tabs span a second row.
    <div className="h-screen h-[100dvh] flex flex-col bg-ground text-ink overflow-hidden">
      <header className="flex-shrink-0 md:h-11 border-b border-line flex flex-wrap md:flex-nowrap items-stretch px-3 md:px-5">
        <h1 className="flex items-center h-10 md:h-auto md:pr-5 md:mr-2 md:border-r border-line text-[15px] font-bold leading-none stretch-expanded tracking-[-0.01em] whitespace-nowrap">
          Music Recommender
        </h1>
        <nav className="order-last md:order-none w-full md:w-auto h-10 md:h-auto flex border-t border-line md:border-t-0 overflow-x-auto no-scrollbar">
          {(["cards", "umap", "analysis", "filter", "upload"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              aria-current={tab === t ? "page" : undefined}
              className="tab flex-1 justify-center md:flex-none"
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
