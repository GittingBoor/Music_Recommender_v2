import type { UmapResponse } from "../types/umap";
import { fetchUmap } from "./api";

interface CachedUmap {
  readonly songCount: number;
  readonly response: Promise<UmapResponse>;
}

let cached: CachedUmap | null = null;

/**
 * The default (all features) UMAP, fetched once per library size and shared:
 * the app requests it on start, the UMAP view picks the same request up.
 */
export function loadDefaultUmap(songCount: number): Promise<UmapResponse> {
  if (cached?.songCount === songCount) return cached.response;
  const entry: CachedUmap = { songCount, response: fetchUmap() };
  cached = entry;
  // A failed request must not be served from the cache forever.
  entry.response.catch(() => {
    if (cached === entry) cached = null;
  });
  return entry.response;
}
