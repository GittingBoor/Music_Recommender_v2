import { useEffect, useState } from "react";
import { useAccount } from "../../account/useAccount";
import { clearSpotifyParam, readSpotifyNotice } from "../../account/spotifyNotice";
import type { Notice } from "../../account/spotifyNotice";
import { ApiError, fetchSpotifyPlaylists, importSpotifyPlaylist } from "../../services/api";
import type { SpotifyImport as SpotifyImportEntry, SpotifyPlaylist } from "../../services/api";
import { Link } from "../../router";
import { SpotifyConnectButton } from "../account/SpotifyConnectButton";
import { ErrorLine, NoticeLine, errorMessage } from "../Notice";
import { SpotifyImportList } from "./SpotifyImportList";
import { useSpotifyImports } from "./useSpotifyImports";

const RETURN_PATH = "/upload";
const COVER_PX = 40;

/** 409 from the playlists call: never connected or the token expired. */
const NEEDS_RECONNECT = 409;

function PlaylistRow({ playlist, busy, onImport }: {
  readonly playlist: SpotifyPlaylist;
  readonly busy: boolean;
  readonly onImport: () => void;
}) {
  const meta = [
    `${playlist.track_count} Songs`,
    playlist.owner,
    playlist.last_import_id !== null ? "schon importiert" : null,
  ].filter(Boolean).join(" · ");

  return (
    <li className="flex items-center gap-3 border-b border-line py-2">
      {playlist.image ? (
        <img
          src={playlist.image}
          alt=""
          width={COVER_PX}
          height={COVER_PX}
          loading="lazy"
          className="h-10 w-10 shrink-0 bg-raised object-cover"
        />
      ) : (
        <div className="h-10 w-10 shrink-0 bg-raised" aria-hidden="true" />
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-ink">{playlist.name}</p>
        <p className="truncate font-mono text-2xs text-ink-3">{meta}</p>
      </div>
      <button
        type="button"
        onClick={onImport}
        disabled={busy}
        aria-label={`${playlist.name} importieren`}
        className="btn"
      >
        {busy ? "Startet…" : "Importieren"}
      </button>
    </li>
  );
}

/** The account's Spotify playlists, each importable with one click. */
function SpotifyPlaylists({ onImported }: { readonly onImported: (started: SpotifyImportEntry) => void }) {
  const [playlists, setPlaylists] = useState<readonly SpotifyPlaylist[] | null>(null);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [importing, setImporting] = useState<ReadonlySet<string>>(new Set());
  const [importError, setImportError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSpotifyPlaylists()
      .then((p) => { if (!cancelled) setPlaylists(p); })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(err instanceof Error ? err : new Error(String(err)));
      });
    return () => { cancelled = true; };
  }, []);

  async function start(playlist: SpotifyPlaylist): Promise<void> {
    setImporting((prev) => new Set(prev).add(playlist.id));
    setImportError(null);
    try {
      const started = await importSpotifyPlaylist(playlist.id);
      onImported(started);
      setPlaylists((prev) =>
        prev?.map((p) => (p.id === playlist.id ? { ...p, last_import_id: started.id } : p)) ?? prev,
      );
    } catch (err: unknown) {
      setImportError(`„${playlist.name}“: ${errorMessage(err)}`);
    } finally {
      setImporting((prev) => {
        const next = new Set(prev);
        next.delete(playlist.id);
        return next;
      });
    }
  }

  if (loadError instanceof ApiError && loadError.status === NEEDS_RECONNECT) {
    return (
      <div className="space-y-3">
        <ErrorLine message={loadError.message} />
        <SpotifyConnectButton next={RETURN_PATH} label="Spotify neu verbinden" />
      </div>
    );
  }
  if (loadError) return <ErrorLine message={loadError.message} />;

  return (
    <div className="space-y-2">
      <p className="t-label border-b border-line pb-1.5">
        Deine Playlists{playlists && <span className="text-ink-4"> · {playlists.length}</span>}
      </p>
      {importError && <ErrorLine message={importError} />}
      {playlists === null && <p className="font-mono text-xs text-ink-3">Lade Playlists von Spotify…</p>}
      {playlists?.length === 0 && (
        <p className="font-mono text-xs text-ink-3">Bei Spotify gibt es keine eigenen oder gespeicherten Playlists.</p>
      )}
      {playlists && playlists.length > 0 && (
        <ul className="-mt-2">
          {playlists.map((p) => (
            <PlaylistRow
              key={p.id}
              playlist={p}
              busy={importing.has(p.id)}
              onImport={() => { void start(p); }}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

/** Connected state: playlists on the left, the imports they started on the right. */
function ConnectedImport() {
  const { imports, error, add } = useSpotifyImports();
  return (
    <div className="grid grid-cols-1 gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="min-w-0">
        <SpotifyPlaylists onImported={add} />
      </div>
      <div className="min-w-0 lg:border-l lg:border-line lg:pl-12">
        <SpotifyImportList imports={imports} error={error} />
      </div>
    </div>
  );
}

/** Upload page section: import whole Spotify playlists into the library. */
export function SpotifyImport() {
  const account = useAccount();
  const [notice] = useState<Notice | null>(readSpotifyNotice);

  useEffect(clearSpotifyParam, []);

  return (
    <section className="space-y-4" aria-labelledby="spotify-import-heading">
      <h2 id="spotify-import-heading" className="t-section">Spotify-Playlists</h2>
      {notice && <div className="max-w-xl"><NoticeLine notice={notice} /></div>}

      {account === undefined && <p className="font-mono text-xs text-ink-3">Lade Account…</p>}
      {account === null && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
          <p className="text-sm text-ink-2">Melde dich an, um deine Spotify-Playlists zu importieren.</p>
          <Link to="/account" className="btn h-8 px-3">Anmelden</Link>
        </div>
      )}
      {account && !account.spotify && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
          <p className="text-sm text-ink-2">Verbinde Spotify, um deine Playlists zu importieren.</p>
          <SpotifyConnectButton next={RETURN_PATH} />
        </div>
      )}
      {account?.spotify && <ConnectedImport key={account.spotify.spotify_user_id} />}
    </section>
  );
}
