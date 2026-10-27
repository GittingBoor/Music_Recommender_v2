import { useCallback, useEffect, useState } from "react";
import { useAccount } from "../../account/useAccount";
import { fetchMyPlaylists, syncMyPlaylists, ApiError } from "../../services/api";
import type { MyPlaylist } from "../../services/api";
import { SpotifyConnectButton } from "../account/SpotifyConnectButton";

/**
 * The logged-in account's Spotify playlists as views on the shared library.
 * Reloaded whenever `libraryVersion` changes (new songs may join a playlist).
 */
export function useMyPlaylists(libraryVersion: number) {
  const account = useAccount();
  const [playlists, setPlaylists] = useState<readonly MyPlaylist[]>([]);
  const loggedIn = !!account;

  useEffect(() => {
    if (!loggedIn) {
      setPlaylists([]);
      return;
    }
    let cancelled = false;
    fetchMyPlaylists()
      .then((p) => { if (!cancelled) setPlaylists(p); })
      .catch((err: unknown) => console.error("Playlists could not be loaded:", err));
    return () => { cancelled = true; };
  }, [loggedIn, libraryVersion]);

  return { account, playlists, setPlaylists };
}

interface Props {
  readonly playlists: readonly MyPlaylist[];
  readonly onPlaylistsChange: (playlists: readonly MyPlaylist[]) => void;
  /** Selected playlist id, null = the whole library. */
  readonly selected: number | null;
  readonly onSelect: (id: number | null) => void;
  readonly spotifyConnected: boolean;
}

/** "All songs" or one of my playlists, plus a button that compares them with Spotify again. */
export function PlaylistScope({ playlists, onPlaylistsChange, selected, onSelect, spotifyConnected }: Props) {
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [reconnect, setReconnect] = useState(false);

  const sync = useCallback(async () => {
    setSyncing(true);
    setMessage(null);
    setReconnect(false);
    try {
      const result = await syncMyPlaylists();
      onPlaylistsChange(result.playlists);
      if (result.liked_needs_reconnect) {
        setMessage("Liked songs need a fresh Spotify connection.");
        setReconnect(true);
      }
      if (selected != null && !result.playlists.some((p) => p.id === selected)) onSelect(null);
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Sync failed.");
      setReconnect(err instanceof ApiError && err.status === 409);
    } finally {
      setSyncing(false);
    }
  }, [onPlaylistsChange, onSelect, selected]);

  if (!spotifyConnected && playlists.length === 0) return null;

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <select
        value={selected ?? ""}
        onChange={(e) => onSelect(e.target.value === "" ? null : Number(e.target.value))}
        className={`field-select h-8 text-xs max-w-full md:max-w-72 ${selected != null ? "border-signal" : ""}`}
        aria-label="Show songs of"
      >
        <option value="">All songs</option>
        {playlists.map((p) => (
          <option key={p.id} value={p.id}>
            {p.kind === "liked" ? "♥ " : ""}{p.name} ({p.song_ids.length}/{p.track_count})
          </option>
        ))}
      </select>
      {spotifyConnected && (
        <button
          onClick={sync}
          disabled={syncing}
          className="btn h-8"
          title="Read your playlists and liked songs from Spotify again and match them with the library"
        >
          {syncing ? "Syncing…" : playlists.length ? "Sync Spotify" : "Load my Spotify playlists"}
        </button>
      )}
      {message && <span className={`font-mono text-2xs ${reconnect ? "text-warn" : "text-bad"}`}>{message}</span>}
      {reconnect && <SpotifyConnectButton next="/account" label="Reconnect" />}
    </div>
  );
}
