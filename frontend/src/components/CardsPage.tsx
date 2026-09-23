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
      <div className="max-w-5xl mx-auto px-4 py-6">
        {songs.length === 0 ? (
          <div className="text-gray-500 text-center py-16 text-sm">
            No songs in the database yet.
          </div>
        ) : (
          <>
            {/* ── sort bar ── */}
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs text-gray-500 uppercase tracking-wider">Sort</span>
              <select
                value={sortKey}
                onChange={(e) => onSortKeyChange(e.target.value)}
                className="bg-gray-900 border border-gray-800 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-violet-500"
              >
                <option value="">Database order</option>
                {SORT_OPTIONS.map((o) => (
                  <option key={o.key} value={o.key}>{o.label}</option>
                ))}
              </select>
              <button
                onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
                disabled={sortKey === ""}
                className="px-2.5 py-1.5 rounded-lg border border-gray-800 text-xs text-gray-300 hover:border-gray-600 transition-colors disabled:opacity-40 disabled:hover:border-gray-800"
                title={sortDir === "asc" ? "Ascending — click for descending" : "Descending — click for ascending"}
              >
                {sortDir === "asc" ? "▲" : "▼"}
              </button>
            </div>

            <div className="space-y-2">
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
