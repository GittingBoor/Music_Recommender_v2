import { useEffect, useMemo, useRef, useState } from "react";
import type { Song } from "../types/song";
import { setQueue } from "../audio/player";
import { SongCard } from "./SongCard";

type SortDir = "asc" | "desc";

interface SortOption {
  key: string;
  label: string;
  get: (s: Song) => string | number | null;
  defaultDir: SortDir;
}

/** Deliberately short list — the Filter page is the place for real sorting. */
const SORT_OPTIONS: SortOption[] = [
  { key: "title",        label: "Title",        defaultDir: "asc",  get: (s) => s.title },
  { key: "artist",       label: "Artist",       defaultDir: "asc",  get: (s) => s.artist },
  { key: "bpm",          label: "BPM",          defaultDir: "desc", get: (s) => s.dsp_features?.bpm ?? null },
  { key: "duration",     label: "Length",       defaultDir: "desc", get: (s) => s.file_metadata?.duration_seconds ?? null },
  { key: "danceability", label: "Danceability", defaultDir: "desc", get: (s) => s.dsp_features?.danceability ?? null },
];

interface Props {
  songs: Song[];
}

export function CardsPage({ songs }: Props) {
  const [sortKey, setSortKey] = useState<string>("");   // "" = database order
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const sorted = useMemo(() => {
    const opt = SORT_OPTIONS.find((o) => o.key === sortKey);
    if (!opt) return songs;
    const dir = sortDir === "asc" ? 1 : -1;
    return [...songs].sort((a, b) => {
      const va = opt.get(a);
      const vb = opt.get(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1; // missing values always sort last
      if (vb == null) return -1;
      if (typeof va === "string" || typeof vb === "string") {
        return dir * String(va).localeCompare(String(vb));
      }
      return dir * (va - vb);
    });
  }, [songs, sortKey, sortDir]);

  // The play queue follows the visible order while this page is open.
  useEffect(() => {
    setQueue(sorted.map((s) => s.id));
  }, [sorted]);

  // Restore the default queue (full library, DB order) when leaving the page.
  const allSongsRef = useRef(songs);
  allSongsRef.current = songs;
  useEffect(() => {
    return () => setQueue(allSongsRef.current.map((s) => s.id));
  }, []);

  function onSortKeyChange(key: string) {
    setSortKey(key);
    const opt = SORT_OPTIONS.find((o) => o.key === key);
    if (opt) setSortDir(opt.defaultDir);
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto px-6 pt-4 pb-10">
        {songs.length === 0 ? (
          <div className="font-mono text-xs text-ink-3 text-center py-16">
            No songs in the database yet.
          </div>
        ) : (
          <>
            {/* ── sort bar ── */}
            <div className="flex items-center gap-2 pb-3 border-b border-line-strong">
              <span className="t-label mr-1">Sort</span>
              <select
                value={sortKey}
                onChange={(e) => onSortKeyChange(e.target.value)}
                className="field-select h-7 text-xs"
              >
                <option value="">Database order</option>
                {SORT_OPTIONS.map((o) => (
                  <option key={o.key} value={o.key}>{o.label}</option>
                ))}
              </select>
              <button
                onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
                disabled={sortKey === ""}
                className="btn w-7 px-0"
                title={sortDir === "asc" ? "Ascending — click for descending" : "Descending — click for ascending"}
                aria-label={sortDir === "asc" ? "Ascending" : "Descending"}
              >
                <svg
                  className={`w-3 h-3 ${sortDir === "desc" ? "rotate-180" : ""}`}
                  viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={1.5}
                >
                  <path d="M6 10.5V1.5M2 5.5l4-4 4 4" />
                </svg>
              </button>
            </div>

            <div>
              {sorted.map((song) => (
                <SongCard key={song.id} song={song} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
