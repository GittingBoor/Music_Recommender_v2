import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { ResultsTable } from "../songs/ResultsTable";
import { ErrorLine, NoticeLine, errorMessage } from "../Notice";

const RETURN_PATH = "/spotify";

export const spotifyPlaylistPath = (id: number) => `/spotify/${id}`;

const DATE_FORMAT = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
});

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

function PlaylistOverview({ playlists, onSynced }: {
  readonly playlists: readonly MyPlaylist[];
  readonly onSynced: (playlists: readonly MyPlaylist[]) => void;
}) {
  const syncAll = useCallback(async () => {
    const result = await syncMyPlaylists();
    onSynced(result.playlists);
    return result.liked_needs_reconnect ? "Lieblingssongs brauchen eine neue Spotify-Verbindung." : null;
  }, [onSynced]);

  return (
    <div className="mx-auto max-w-4xl space-y-3 px-6 pb-16 pt-6">
      <h2 className="t-section">Spotify</h2>
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line pb-2">
        <p className="t-label">Deine Playlists{playlists.length > 0 && <> · {playlists.length}</>}</p>
        <SyncButton
          label={playlists.length ? "Alle mit Spotify abgleichen" : "Playlists von Spotify holen"}
          busyLabel="Gleiche ab…"
          title="Liest geänderte Playlists und deine Lieblingssongs neu von Spotify"
          run={syncAll}
        />
      </div>
      {playlists.length === 0 ? (
        <p className="max-w-xl text-sm text-ink-2">
          Noch keine Playlists geholt. Importiere eine Playlist unter{" "}
          <Link to="/upload" className="underline decoration-line-strong underline-offset-4 hover:decoration-ink-3">Upload</Link>{" "}
          oder hole alle Playlists und Lieblingssongs mit dem Button oben.
        </p>
      ) : (
        <ul className="-mt-3">
          {playlists.map((p) => (
            <li key={p.id} className="border-b border-line">
              <Link to={spotifyPlaylistPath(p.id)} className="group flex items-baseline gap-3 py-2.5 hover:bg-raised">
                <span className="min-w-0 flex-1 truncate text-sm text-ink group-hover:underline group-hover:decoration-line-strong group-hover:underline-offset-4">
                  <PlaylistName playlist={p} />
                </span>
                <span className="shrink-0 font-mono text-2xs tabular-nums text-ink-3">
                  <span className="text-ink">{p.song_ids.length}</span> Songs
                  <span className="text-ink-4"> · {p.track_count} auf Spotify</span>
                </span>
                <span className="hidden w-28 shrink-0 text-right font-mono text-2xs tabular-nums text-ink-4 md:inline" title="Zuletzt von Spotify gelesen">
                  {DATE_FORMAT.format(new Date(p.synced_at))}
                </span>
              </Link>
            </li>
          ))}
        </ul>
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

  return (
    <div className="space-y-3 px-3 py-3 md:space-y-4 md:px-4 md:py-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Link to={RETURN_PATH} className="btn-quiet shrink-0">← Playlists</Link>
        <h2 className="t-section min-w-0 flex-1 truncate"><PlaylistName playlist={playlist} /></h2>
        <span className="hidden font-mono text-2xs tabular-nums text-ink-4 md:inline" title="Zuletzt von Spotify gelesen">
          abgeglichen {DATE_FORMAT.format(new Date(playlist.synced_at))}
        </span>
        <SyncButton
          label="Playlist abgleichen"
          busyLabel="Gleiche ab…"
          title="Liest diese Playlist neu von Spotify, falls sie sich geändert hat"
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
  if (playlistId === null) return <PlaylistOverview playlists={playlists} onSynced={setPlaylists} />;

  const playlist = playlists.find((p) => p.id === playlistId);
  if (!playlist) {
    return (
      <div className="space-y-3 px-6 pt-6">
        <p className="font-mono text-xs text-ink-3">Diese Playlist gibt es nicht (mehr).</p>
        <Link to={RETURN_PATH} className="btn-quiet">← Playlists</Link>
      </div>
    );
  }
  return <PlaylistView key={playlist.id} playlist={playlist} library={library} active={active} onSynced={replaceOne} />;
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

  return (
    <div className="h-full overflow-y-auto">
      {notice && <div className="mx-auto max-w-4xl px-6 pt-6"><NoticeLine notice={notice} /></div>}
      {account === undefined && <p className="px-6 pt-6 font-mono text-xs text-ink-3">Lade Account…</p>}
      {account === null && (
        <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-x-4 gap-y-3 px-6 pt-6">
          <p className="text-sm text-ink-2">Melde dich an, um deine Spotify-Playlists zu sehen.</p>
          <Link to="/account" className="btn h-8 px-3">Anmelden</Link>
        </div>
      )}
      {account && !account.spotify && (
        <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-x-4 gap-y-3 px-6 pt-6">
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
