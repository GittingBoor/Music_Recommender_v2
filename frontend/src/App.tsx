import { useEffect, useRef, useState } from "react";
import { fetchSongs } from "./services/api";
import type { Song } from "./types/song";
import { SongCard } from "./components/SongCard";
import { UmapView } from "./components/UmapView";

type Tab = "cards" | "umap";

const POLL_INTERVAL_MS = 8_000;

export default function App() {
  const [songs, setSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("cards");
  const songsRef = useRef<Song[]>([]);

  const refreshSongs = () =>
    fetchSongs()
      .then((data) => {
        songsRef.current = data;
        setSongs(data);
      })
      .catch(() => {});

  // Initial load
  useEffect(() => {
    fetchSongs()
      .then((data) => {
        songsRef.current = data;
        setSongs(data);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Poll for new songs while app is open (catches ingestion updates)
  useEffect(() => {
    if (loading) return;
    const id = setInterval(refreshSongs, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [loading]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-white overflow-hidden">
      <header className="flex-shrink-0 border-b border-gray-800 px-6 py-3 flex items-center gap-6">
        <div className="min-w-0">
          <h1 className="text-lg font-bold tracking-tight leading-none">
            Music Recommender
          </h1>
          {!loading && !error && (
            <p className="text-xs text-gray-500 mt-0.5">{songs.length} songs</p>
          )}
        </div>
        <nav className="flex gap-1">
          {(["cards", "umap"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                tab === t
                  ? "bg-gray-800 text-white"
                  : "text-gray-500 hover:text-gray-300 hover:bg-gray-900"
              }`}
            >
              {t === "cards" ? "Cards" : "UMAP"}
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
            {tab === "cards" && (
              <div className="h-full overflow-y-auto">
                <div className="max-w-5xl mx-auto px-4 py-6">
                  {songs.length === 0 ? (
                    <div className="text-gray-500 text-center py-16 text-sm">
                      No songs in the database yet.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {songs.map((song) => (
                        <SongCard key={song.id} song={song} />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
            {tab === "umap" && <UmapView songs={songs} />}
          </>
        )}
      </main>
    </div>
  );
}
