import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useAccount } from "../../account/useAccount";
import { clearSpotifyParam, readSpotifyNotice } from "../../account/spotifyNotice";
import type { Notice } from "../../account/spotifyNotice";
import { setQueue } from "../../audio/player";
import {
  ApiError, fetchMyPlaylistTracks, fetchMyPlaylists, syncMyPlaylist, syncMyPlaylists,
} from "../../services/api";
import type { MyPlaylist } from "../../services/api";
import type { Song } from "../../types/song";
import { Link } from "../../router";
import { SpotifyConnectButton } from "../account/SpotifyConnectButton";
import { SegmentedControl } from "../SegmentedControl";
import type { Segment } from "../SegmentedControl";
import { ResultsTable } from "../songs/ResultsTable";
import { ErrorLine, NoticeLine, errorMessage } from "../Notice";

const RETURN_PATH = "/spotify";

export const spotifyPlaylistPath = (id: number) => `/spotify/${id}`;

const DATE_FORMAT = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
});

type SectionId = "own" | "shared" | "albums";
type PlaylistFilter = "all" | SectionId;

interface PlaylistSection {
  readonly id: SectionId;
  readonly heading: string;
  readonly filterLabel: string;
  readonly matches: (playlist: MyPlaylist) => boolean;
}

const SECTIONS: readonly PlaylistSection[] = [
  {
    id: "own",
    heading: "Eigene Playlists",
    filterLabel: "Eigene",
    matches: (p) => p.kind === "liked" || (p.kind === "playlist" && !p.collaborative),
  },
  {
    id: "shared",
    heading: "Gemeinsame Playlists",
    filterLabel: "Gemeinsam",
    matches: (p) => p.kind === "playlist" && p.collaborative,
  },
  { id: "albums", heading: "Alben", filterLabel: "Alben", matches: (p) => p.kind === "album" },
];

/** The API's order, except that the liked songs always lead. */
function playlistsOf(section: PlaylistSection, playlists: readonly MyPlaylist[]): readonly MyPlaylist[] {
  return playlists
    .filter(section.matches)
    .sort((a, b) => Number(b.kind === "liked") - Number(a.kind === "liked"));
}

function matchesSearch(playlist: MyPlaylist, query: string): boolean {
  return playlist.name.toLowerCase().includes(query) || (playlist.artists?.toLowerCase().includes(query) ?? false);
}

function PlaylistName({ playlist }: { readonly playlist: MyPlaylist }) {
  return (
    <>
      {playlist.kind === "liked" && <span className="mr-1.5 text-ink-3" aria-hidden="true">♥</span>}
      {playlist.name}
    </>
  );
}

/** A Spotify sync button with its error line; `run` returns a reconnect hint to show, or null. */
function SyncButton({ label, busyLabel, title, run }: {
  readonly label: string;
  readonly busyLabel: string;
  readonly title: string;
  readonly run: () => Promise<string | null>;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [reconnect, setReconnect] = useState(false);

  async function click(): Promise<void> {
    setBusy(true);
    setMessage(null);
    setReconnect(false);
    try {
      const warning = await run();
      if (warning) {
        setMessage(warning);
        setReconnect(true);
      }
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Abgleich fehlgeschlagen.");
      setReconnect(err instanceof ApiError && err.status === 409);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
      {message && <span className={`font-mono text-2xs ${reconnect ? "text-warn" : "text-bad"}`}>{message}</span>}
      {reconnect && <SpotifyConnectButton next={RETURN_PATH} label="Neu verbinden" />}
      <button
        onClick={() => { void click(); }}
        disabled={busy}
        aria-busy={busy}
        className="btn h-8 shrink-0"
        title={title}
      >
        {busy ? busyLabel : label}
      </button>
    </div>
  );
}

/** As many columns as fit; a future section of playlists is a label above one of these. */
function PlaylistGrid({ playlists }: { readonly playlists: readonly MyPlaylist[] }) {
  return (
    <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,20rem),1fr))] gap-x-8">
      {playlists.map((p) => (
        <li key={p.id} className="min-w-0 border-b border-line">
          <Link to={spotifyPlaylistPath(p.id)} className="group -mx-2 block space-y-0.5 px-2 py-2.5 hover:bg-raised">
            <span className="block truncate text-sm text-ink group-hover:underline group-hover:decoration-line-strong group-hover:underline-offset-4">
              <PlaylistName playlist={p} />
            </span>
            {p.artists && <span className="block truncate text-xs text-ink-3">{p.artists}</span>}
            <span className="flex flex-wrap justify-between gap-x-3 font-mono text-2xs tabular-nums text-ink-3">
              <span className="whitespace-nowrap">
                <span className="text-ink">{p.song_ids.length}</span> Songs
                <span className="text-ink-4"> · {p.track_count} auf Spotify</span>
              </span>
              <span className="whitespace-nowrap text-ink-4" title="Zuletzt von Spotify gelesen">
                {DATE_FORMAT.format(new Date(p.synced_at))}
              </span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function PlaylistOverview({ playlists, onSynced }: {
  readonly playlists: readonly MyPlaylist[];
  readonly onSynced: (playlists: readonly MyPlaylist[]) => void;
}) {
  const [filter, setFilter] = useState<PlaylistFilter>("all");
  const [search, setSearch] = useState("");

  const syncAll = useCallback(async () => {
    const result = await syncMyPlaylists();
    onSynced(result.playlists);
    return result.liked_needs_reconnect ? "Lieblingssongs brauchen eine neue Spotify-Verbindung." : null;
  }, [onSynced]);

  const sections = useMemo(
    () => SECTIONS.map((section) => ({ section, items: playlistsOf(section, playlists) })),
    [playlists],
  );
  // A filter that lost its last entry in a sync falls back to everything.
  const activeFilter = sections.find((s) => s.section.id === filter)?.items.length === 0 ? "all" : filter;
  const query = search.trim().toLowerCase();
  const visible = sections
    .filter((s) => activeFilter === "all" || s.section.id === activeFilter)
    .map((s) => ({ ...s, items: s.items.filter((p) => matchesSearch(p, query)) }))
    .filter((s) => s.items.length > 0);
  const segments: readonly Segment<PlaylistFilter>[] = [
    { id: "all", label: "Alle", count: playlists.length },
    ...sections.map((s) => ({
      id: s.section.id, label: s.section.filterLabel, count: s.items.length, disabled: s.items.length === 0,
    })),
  ];

  return (
    <div className="space-y-3 px-6 pb-16 pt-6">
      <div className="flex flex-wrap items-end justify-end gap-3 md:justify-between">
        <p className="t-label hidden md:block">Playlists und Alben</p>
        <SyncButton
          label={playlists.length ? "Alle mit Spotify abgleichen" : "Von Spotify holen"}
          busyLabel="Gleiche ab…"
          title="Liest geänderte Playlists, deine Lieblingssongs und Alben neu von Spotify"
          run={syncAll}
        />
      </div>
      {playlists.length === 0 ? (
        <p className="max-w-xl text-sm text-ink-2">
          Noch nichts geholt. Importiere eine Playlist unter{" "}
          <Link to="/upload" className="underline decoration-line-strong underline-offset-4 hover:decoration-ink-3">Upload</Link>{" "}
          oder hole alle Playlists, Lieblingssongs und Alben mit dem Button oben.
        </p>
      ) : (
        <>
          <div className="sticky top-0 z-10 -mx-6 flex flex-wrap items-center gap-2 border-b border-line bg-ground px-6 py-2">
            <SegmentedControl
              label="Nach Art filtern"
              segments={segments}
              value={activeFilter}
              onChange={setFilter}
              className="flex w-full md:inline-flex md:w-auto"
            />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Name oder Künstler suchen…"
              aria-label="Playlists und Alben nach Name oder Künstler suchen"
              className="field h-10 w-full min-w-0 md:w-auto md:flex-1 lg:ml-auto lg:h-8 lg:w-72 lg:flex-none"
            />
          </div>
          {visible.length === 0 ? (
            <p className="pt-3 font-mono text-xs text-ink-3">Nichts gefunden für „{search.trim()}“.</p>
          ) : (
            <div className="space-y-8 pt-3">
              {visible.map(({ section, items }) => (
                <section key={section.id} className="space-y-0.5">
                  <h2 className="t-section border-b border-line pb-1.5">
                    {section.heading}<span className="t-label font-normal"> · {items.length}</span>
                  </h2>
                  <PlaylistGrid playlists={items} />
                </section>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** One playlist as a sortable song table: only its songs that are in the library. */
function PlaylistView({ playlist, library, active, onSynced }: {
  readonly playlist: MyPlaylist;
  readonly library: readonly Song[];
  readonly active: boolean;
  readonly onSynced: (playlist: MyPlaylist) => void;
}) {
  const [songIds, setSongIds] = useState<readonly string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  // Matched with the library on the server each time: new songs show up without a Spotify call.
  useEffect(() => {
    let cancelled = false;
    fetchMyPlaylistTracks(playlist.id)
      .then((tracks) => {
        if (cancelled) return;
        setSongIds([...new Set(tracks.flatMap((t) => (t.song_id ? [t.song_id] : [])))]);
        setError(null);
      })
      .catch((err: unknown) => { if (!cancelled) setError(errorMessage(err)); });
    return () => { cancelled = true; };
  }, [playlist.id, playlist.synced_at, library.length]);

  const songs = useMemo(() => {
    if (!songIds) return [];
    const byId = new Map(library.map((s) => [s.id, s]));
    return songIds.flatMap((id) => byId.get(id) ?? []);
  }, [songIds, library]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    if (!q) return songs;
    return songs.filter((s) => s.title?.toLowerCase().includes(q) || s.artist?.toLowerCase().includes(q));
  }, [songs, search]);

  // The visible order is the play queue while the page is shown (as on the Songs page);
  // leaving it, or switching to another playlist, restores the whole library.
  const visibleOrderRef = useRef<string[]>([]);
  const activeRef = useRef(active);
  activeRef.current = active;
  const handleVisibleOrderChange = useCallback((ids: string[]) => {
    visibleOrderRef.current = ids;
    if (activeRef.current) setQueue(ids);
  }, []);
  const libraryRef = useRef(library);
  libraryRef.current = library;
  useEffect(() => {
    // Empty until the table has its rows; it sets the queue itself once they are there.
    if (active && visibleOrderRef.current.length > 0) setQueue(visibleOrderRef.current);
    return () => setQueue(libraryRef.current.map((s) => s.id));
  }, [active]);

  const syncOne = useCallback(async () => {
    onSynced(await syncMyPlaylist(playlist.id));
    return null;
  }, [onSynced, playlist.id]);

  const album = playlist.kind === "album";

  return (
    <div className="space-y-3 px-3 py-3 md:space-y-4 md:px-4 md:py-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Link to={RETURN_PATH} className="btn-quiet shrink-0">← {album ? "Alben" : "Playlists"}</Link>
        <div className="min-w-0 flex-1">
          <h2 className="t-section truncate"><PlaylistName playlist={playlist} /></h2>
          {playlist.artists && <p className="truncate text-xs text-ink-3">{playlist.artists}</p>}
        </div>
        <span className="hidden font-mono text-2xs tabular-nums text-ink-4 md:inline" title="Zuletzt von Spotify gelesen">
          abgeglichen {DATE_FORMAT.format(new Date(playlist.synced_at))}
        </span>
        <SyncButton
          label={album ? "Album abgleichen" : "Playlist abgleichen"}
          busyLabel="Gleiche ab…"
          title={album
            ? "Liest dieses Album neu von Spotify, falls es sich geändert hat"
            : "Liest diese Playlist neu von Spotify, falls sie sich geändert hat"}
          run={syncOne}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2 md:gap-3">
        <input
          type="text"
          placeholder="Search title or artist…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="field min-w-32 flex-1 md:min-w-48"
        />
        <span className="shrink-0 font-mono text-2xs tabular-nums text-ink-3">
          <span className="text-sm text-ink">{filtered.length}</span> / {songs.length} songs
          <span className="text-ink-4"> · {playlist.track_count} auf Spotify</span>
        </span>
      </div>
      {error && <ErrorLine message={error} />}
      {songIds === null && !error && <p className="font-mono text-xs text-ink-3">Lade Songs…</p>}
      {songIds !== null && songs.length === 0 && (
        <p className="font-mono text-xs text-ink-3">Noch keiner dieser Songs ist in der Bibliothek.</p>
      )}
      {songs.length > 0 && (
        <ResultsTable key={playlist.id} songs={filtered} onVisibleOrderChange={handleVisibleOrderChange} />
      )}
    </div>
  );
}

function ConnectedSpotify({ library, playlistId, active }: {
  readonly library: readonly Song[];
  readonly playlistId: number | null;
  readonly active: boolean;
}) {
  const [playlists, setPlaylists] = useState<readonly MyPlaylist[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reloaded when the library grows: new songs may be in a playlist.
  useEffect(() => {
    let cancelled = false;
    fetchMyPlaylists()
      .then((p) => { if (!cancelled) { setPlaylists(p); setError(null); } })
      .catch((err: unknown) => { if (!cancelled) setError(errorMessage(err)); });
    return () => { cancelled = true; };
  }, [library.length]);

  const replaceOne = useCallback((changed: MyPlaylist) => {
    setPlaylists((all) => all?.map((p) => (p.id === changed.id ? changed : p)) ?? null);
  }, []);

  if (error) return <div className="px-6 pt-6"><ErrorLine message={error} /></div>;
  if (playlists === null) return <p className="px-6 pt-6 font-mono text-xs text-ink-3">Lade Playlists…</p>;

  const playlist = playlists.find((p) => p.id === playlistId);
  return (
    <>
      {/* Stays mounted: search and filter survive a look into one playlist. */}
      <div hidden={playlistId !== null}>
        <PlaylistOverview playlists={playlists} onSynced={setPlaylists} />
      </div>
      {playlist && (
        <PlaylistView key={playlist.id} playlist={playlist} library={library} active={active} onSynced={replaceOne} />
      )}
      {playlistId !== null && !playlist && (
        <div className="space-y-3 px-6 pt-6">
          <p className="font-mono text-xs text-ink-3">Diese Playlist gibt es nicht (mehr).</p>
          <Link to={RETURN_PATH} className="btn-quiet">← Playlists</Link>
        </div>
      )}
    </>
  );
}

/** /spotify: the account's stored playlists; /spotify/:id: one of them as a song table.
 *  Stays mounted while hidden (`active` false), so a playlist keeps its sort and scroll. */
export function SpotifyPage({ songs, playlistId, active }: {
  readonly songs: readonly Song[];
  readonly playlistId: number | null;
  readonly active: boolean;
}) {
  const account = useAccount();
  const [notice] = useState<Notice | null>(readSpotifyNotice);

  useEffect(clearSpotifyParam, []);

  // Overview and playlist share this scroller: a playlist opens at its top,
  // going back returns to the spot in the (long) overview.
  const scrollRef = useRef<HTMLDivElement>(null);
  const overviewScroll = useRef(0);
  useLayoutEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = playlistId === null ? overviewScroll.current : 0;
  }, [playlistId]);

  return (
    <div
      ref={scrollRef}
      onScroll={(e) => { if (playlistId === null) overviewScroll.current = e.currentTarget.scrollTop; }}
      className="h-full overflow-y-auto"
    >
      {notice && <div className="px-6 pt-6"><NoticeLine notice={notice} /></div>}
      {account === undefined && <p className="px-6 pt-6 font-mono text-xs text-ink-3">Lade Account…</p>}
      {account === null && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-6 pt-6">
          <p className="text-sm text-ink-2">Melde dich an, um deine Spotify-Playlists zu sehen.</p>
          <Link to="/account" className="btn h-8 px-3">Anmelden</Link>
        </div>
      )}
      {account && !account.spotify && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-6 pt-6">
          <p className="text-sm text-ink-2">Verbinde Spotify, um deine Playlists zu sehen.</p>
          <SpotifyConnectButton next={RETURN_PATH} />
        </div>
      )}
      {account?.spotify && (
        <ConnectedSpotify
          key={account.spotify.spotify_user_id} library={songs} playlistId={playlistId} active={active}
        />
      )}
    </div>
  );
}
