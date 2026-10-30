import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSpotifyImports } from "../../services/api";
import type { SpotifyImport } from "../../services/api";
import { errorMessage } from "../Notice";

const POLL_MS = 5_000;

export interface SpotifyImportsState {
  readonly imports: readonly SpotifyImport[] | null;
  readonly error: string | null;
  /** Puts a just-started import at the top until the next poll returns it. */
  readonly add: (started: SpotifyImport) => void;
  /** Swaps in a changed import at its current place, e.g. after a retry. */
  readonly replace: (changed: SpotifyImport) => void;
}

/** The Spotify account's imports, polled while any of them still has queued tracks.
 *  Starts over when `accountId` changes; null (no Spotify account) loads nothing. */
export function useSpotifyImports(accountId: string | null): SpotifyImportsState {
  const [imports, setImports] = useState<readonly SpotifyImport[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Results that arrive after the account changed belong to the previous one.
  const accountRef = useRef(accountId);
  accountRef.current = accountId;
  const isCurrent = useCallback((): boolean => accountRef.current === accountId, [accountId]);

  const load = useCallback(async (): Promise<void> => {
    if (accountId === null) return;
    try {
      const loaded = await fetchSpotifyImports();
      if (!isCurrent()) return;
      setImports(loaded);
      setError(null);
    } catch (err: unknown) {
      if (isCurrent()) setError(errorMessage(err));
    }
  }, [accountId, isCurrent]);

  useEffect(() => {
    setImports(null);
    setError(null);
    void load();
  }, [load]);

  const running = imports?.some((i) => i.queued > 0) ?? false;
  // The Upload page stays mounted on other pages; a hidden tab skips polls and catches up when shown.
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      if (!document.hidden) void load();
    }, POLL_MS);
    const onVisible = (): void => {
      if (!document.hidden) void load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [running, load]);

  const add = useCallback((started: SpotifyImport): void => {
    if (isCurrent()) setImports((prev) => [started, ...(prev ?? []).filter((i) => i.id !== started.id)]);
  }, [isCurrent]);

  const replace = useCallback((changed: SpotifyImport): void => {
    if (isCurrent()) setImports((prev) => prev?.map((i) => (i.id === changed.id ? changed : i)) ?? [changed]);
  }, [isCurrent]);

  return { imports, error, add, replace };
}
