import { useCallback, useEffect, useState } from "react";
import { fetchSpotifyImports } from "../../services/api";
import type { SpotifyImport } from "../../services/api";
import { errorMessage } from "../Notice";

const POLL_MS = 5_000;

export interface SpotifyImportsState {
  readonly imports: readonly SpotifyImport[] | null;
  readonly error: string | null;
  /** Puts a just-started import at the top until the next poll returns it. */
  readonly add: (started: SpotifyImport) => void;
}

/** The account's imports; polled while any of them still has queued tracks. */
export function useSpotifyImports(): SpotifyImportsState {
  const [imports, setImports] = useState<readonly SpotifyImport[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    try {
      setImports(await fetchSpotifyImports());
      setError(null);
    } catch (err: unknown) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
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
    setImports((prev) => [started, ...(prev ?? []).filter((i) => i.id !== started.id)]);
  }, []);

  return { imports, error, add };
}
