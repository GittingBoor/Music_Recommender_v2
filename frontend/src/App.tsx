import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { fetchNeighbors, fetchSongCount, fetchSongs } from "./services/api";
import type { Song } from "./types/song";
import { SongsPage } from "./components/songs/SongsPage";
import { SongDetailPage } from "./components/songs/SongDetailPage";
import { AnalysisPage, ANALYSIS_SECTIONS } from "./components/analysis/AnalysisPage";
import type { AnalysisSection } from "./components/analysis/AnalysisPage";
import { PlayerBar } from "./components/PlayerBar";
import { UploadPage } from "./components/upload/UploadPage";
import { setNeighborSource, setQueue } from "./audio/player";
import { Link, navigate, usePath } from "./router";

// The player stays free of API imports; the app wires the lookup in once.
setNeighborSource(fetchNeighbors);

type Route =
  | { page: "songs"; songId: string | null }
  | { page: "analysis"; section: AnalysisSection }
  | { page: "upload" }
  | { page: "notfound" };

/** URL → page:  /songs · /songs/:id · /analysis[/umap|/correlations|/timeseries] · /upload */
function matchRoute(path: string): Route {
  const parts = path.split("/").filter(Boolean);
  if (parts.length === 0) return { page: "songs", songId: null }; // "/" is redirected to /songs
  if (parts[0] === "songs" && parts.length <= 2) {
    if (parts.length === 1) return { page: "songs", songId: null };
    try {
      return { page: "songs", songId: decodeURIComponent(parts[1]) };
    } catch {
      return { page: "notfound" };
    }
  }
  if (parts[0] === "analysis") {
    const section = ANALYSIS_SECTIONS.find((s) => s.path === path);
    if (section) return { page: "analysis", section: section.id };
  }
  if (parts[0] === "upload" && parts.length === 1) return { page: "upload" };
  return { page: "notfound" };
}

const NAV: { page: Route["page"]; label: string; to: string }[] = [
  { page: "songs",    label: "Songs",    to: "/songs" },
  { page: "analysis", label: "Analysis", to: "/analysis" },
  { page: "upload",   label: "Upload",   to: "/upload" },
];

function pageTitle(route: Route, songs: Song[]): string {
  switch (route.page) {
    case "songs": {
      if (!route.songId) return "Songs";
      const s = songs.find((x) => x.id === route.songId);
      return s ? `${s.title ?? "Unknown"} – ${s.artist ?? "Unknown artist"}` : "Song";
    }
    case "analysis":
      return `${ANALYSIS_SECTIONS.find((s) => s.id === route.section)?.label ?? "Analysis"} · Analysis`;
    case "upload":
      return "Upload";
    case "notfound":
      return "Not found";
  }
}

const POLL_INTERVAL_MS = 8_000;

/** True from the first render where `active` is set on — keeps a page mounted after its first visit. */
function useVisited(active: boolean): boolean {
  const [visited, setVisited] = useState(active);
  if (active && !visited) setVisited(true);
  return visited || active;
}

/** Full-size layer that stays mounted but hidden while another page is shown.
 *  visibility (not display) keeps the scroll positions inside it intact. */
function KeptPage({ active, children }: { active: boolean; children: ReactNode }) {
  return <div className={`absolute inset-0 ${active ? "" : "invisible"}`}>{children}</div>;
}

export default function App() {
  const [songs, setSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const songsRef = useRef<Song[]>([]);

  const path = usePath();
  const route = matchRoute(path);
  // Songs and Upload keep their state (filters, scroll, running downloads) across page switches.
  const songsVisited = useVisited(route.page === "songs");
  const uploadVisited = useVisited(route.page === "upload");

  useEffect(() => {
    if (path === "/") navigate("/songs", { replace: true });
  }, [path]);

  const title = pageTitle(route, songs);
  useEffect(() => {
    document.title = `${title} · Music Recommender`;
  }, [title]);

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
          <Link to="/songs">Music Recommender</Link>
        </h1>
        <nav className="order-last md:order-none w-full md:w-auto h-10 md:h-auto flex border-t border-line md:border-t-0 overflow-x-auto no-scrollbar">
          {NAV.map((n) => (
            <Link
              key={n.page}
              to={n.to}
              aria-current={route.page === n.page ? "page" : undefined}
              className="tab flex-1 justify-center md:flex-none"
            >
              {n.label}
            </Link>
          ))}
        </nav>
        {!loading && !error && (
          <p className="ml-auto self-center pl-4 font-mono text-2xs text-ink-3 whitespace-nowrap">
            <span className="text-ink">{songs.length}</span> songs
          </p>
        )}
      </header>

      <main className="relative flex-1 overflow-hidden">
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
            {songsVisited && (
              // The list stays mounted (just invisible) under an open song and on
              // other pages, so filters, sort order and scroll position survive.
              <KeptPage active={route.page === "songs" && !route.songId}>
                <SongsPage songs={songs} active={route.page === "songs"} />
              </KeptPage>
            )}
            {route.page === "songs" && route.songId && (
              <div className="absolute inset-0 bg-ground">
                <SongDetailPage key={route.songId} songs={songs} songId={route.songId} />
              </div>
            )}
            {route.page === "analysis" && <AnalysisPage songs={songs} section={route.section} />}
            {uploadVisited && (
              <KeptPage active={route.page === "upload"}>
                <UploadPage />
              </KeptPage>
            )}
            {route.page === "notfound" && (
              <div className="h-full flex flex-col items-center justify-center gap-3 font-mono text-xs text-ink-3">
                <p>Page not found.</p>
                <Link to="/songs" className="btn-quiet">Go to all songs</Link>
              </div>
            )}
          </>
        )}
      </main>
      <PlayerBar songs={songs} />
    </div>
  );
}
