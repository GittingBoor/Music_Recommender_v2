import { useEffect, useMemo, useRef, useState } from "react";
import type { Song } from "../../types/song";
import { PlayButton } from "../PlayButton";

interface Props {
  songs: readonly Song[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** Phones only: closes the overlay without picking a song. */
  onClose?: () => void;
}

const byTitle = (a: Song, b: Song): number =>
  (a.title ?? "").localeCompare(b.title ?? "", undefined, { sensitivity: "base" });

/** Searchable list of the whole library; picking a row makes it the seed song. */
export function SongPicker({ songs, selectedId, onSelect, onClose }: Props) {
  const [search, setSearch] = useState("");
  const selectedRef = useRef<HTMLLIElement>(null);

  const sorted = useMemo(() => [...songs].sort(byTitle), [songs]);
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter(
      (s) => s.title?.toLowerCase().includes(q) || s.artist?.toLowerCase().includes(q),
    );
  }, [sorted, search]);

  // A deep-linked or "more like this" seed may sit far down the list.
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  return (
    <>
      <div className="sticky top-0 z-10 bg-panel border-b border-line px-3 py-3 md:px-4 space-y-2.5">
        <div className="flex items-center justify-between gap-3 min-h-8">
          <h2 className="t-section">Pick a song</h2>
          {onClose && (
            <button onClick={onClose} className="btn h-8 md:hidden">Close</button>
          )}
        </div>
        <div className="flex items-center gap-3">
          <input
            type="text"
            placeholder="Search title or artist…"
            aria-label="Search songs by title or artist"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="field flex-1 min-w-0"
          />
          <span className="font-mono text-2xs text-ink-3 shrink-0 tabular-nums">
            <span className="text-ink">{visible.length}</span> / {songs.length}
          </span>
        </div>
      </div>

      {visible.length === 0 ? (
        <p className="font-mono text-xs text-ink-3 px-4 py-10 text-center">
          No song matches “{search.trim()}”.
        </p>
      ) : (
        <ul>
          {visible.map((song) => {
            const selected = song.id === selectedId;
            return (
              <li
                key={song.id}
                ref={selected ? selectedRef : undefined}
                className={`flex items-center gap-1 pl-1.5 pr-2 md:pl-2.5 border-b border-line ${selected ? "bg-raised" : "hover:bg-raised/60"}`}
              >
                <PlayButton songId={song.id} />
                <button
                  onClick={() => onSelect(song.id)}
                  aria-current={selected ? "true" : undefined}
                  className="flex-1 min-w-0 flex items-center gap-2 py-2 text-left"
                >
                  <span className="min-w-0 flex-1">
                    <span className={`block truncate font-medium ${selected ? "text-signal" : "text-ink"}`}>
                      {song.title ?? "Unknown"}
                    </span>
                    <span className="block truncate text-xs text-ink-3">{song.artist ?? "Unknown artist"}</span>
                  </span>
                  {selected && <span className="font-mono text-2xs text-signal shrink-0">Seed</span>}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
