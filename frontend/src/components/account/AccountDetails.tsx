import { useState } from "react";
import { logout, refreshAccount } from "../../account/useAccount";
import { disconnectSpotify } from "../../services/api";
import type { Account } from "../../services/api";
import { Link } from "../../router";
import { ErrorLine, errorMessage } from "../Notice";
import { SpotifyConnectButton } from "./SpotifyConnectButton";

/** Connect, show or disconnect the account's Spotify link. */
function SpotifySection({ account }: { readonly account: Account }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const spotify = account.spotify;

  async function disconnect(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await disconnectSpotify();
      await refreshAccount();
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3 border-t border-line pt-6" aria-labelledby="spotify-heading">
      <h3 id="spotify-heading" className="t-section">Spotify</h3>
      {spotify ? (
        <>
          <div className="flex items-center gap-3 border-y border-line py-2.5">
            <span className="h-1.5 w-1.5 shrink-0 bg-ok" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-ink">{spotify.display_name ?? spotify.spotify_user_id}</p>
              <p className="font-mono text-2xs text-ink-3">verbunden</p>
            </div>
            <button type="button" onClick={() => { void disconnect(); }} disabled={busy} className="btn h-8 px-3">
              Trennen
            </button>
          </div>
          <Link to="/upload" className="btn-quiet inline-block">Playlists auf der Upload-Seite importieren</Link>
        </>
      ) : (
        <>
          <p className="text-xs text-ink-2 leading-relaxed">
            Verbinde Spotify, um deine Playlists auf der Upload-Seite zu importieren.
          </p>
          <SpotifyConnectButton next="/account" />
        </>
      )}
      {error && <ErrorLine message={error} />}
    </section>
  );
}

/** The logged-in view: who is logged in, Spotify, logout. */
export function AccountDetails({ account }: { readonly account: Account }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signOut(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await logout();
    } catch (err: unknown) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1.5">
        <p className="t-label">Angemeldet als</p>
        <p className="break-all font-mono text-sm text-ink">{account.email}</p>
      </div>

      <SpotifySection account={account} />

      <div className="space-y-3 border-t border-line pt-6">
        <button type="button" onClick={() => { void signOut(); }} disabled={busy} className="btn h-8 px-3">
          Abmelden
        </button>
        {error && <ErrorLine message={error} />}
      </div>
    </div>
  );
}
