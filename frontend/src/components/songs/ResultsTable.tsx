import { Fragment, useEffect, useMemo, useState } from "react";
import type { Song } from "../../types/song";
import { PlayButton } from "../PlayButton";
import { SongDetails } from "../SongDetails";

type SortDir = "asc" | "desc";

interface Column {
  key: string;
  label: string;
  get: (s: Song) => string | number | null;
  /** Direction used on the first click of this column. */
  defaultDir: SortDir;
  format?: (v: number) => string;
  align?: "left" | "right";
  cellClass?: string;
  /** Max cell width — text beyond it is truncated. Defaults to max-w-56. */
  widthClass?: string;
}

function fmtDuration(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

const score = (v: number) => v.toFixed(2);

const MOOD_KEYS = ["happy", "sad", "aggressive", "party", "relaxed", "acoustic", "electronic"] as const;

const COLUMNS: Column[] = [
  {
    key: "title", label: "Title", defaultDir: "asc",
    get: (s) => s.title,
    cellClass: "font-medium text-ink",
    widthClass: "max-w-40",
  },
  {
    key: "artist", label: "Artist", defaultDir: "asc",
    get: (s) => s.artist,
    cellClass: "text-ink-2",
    widthClass: "max-w-32",
  },
  {
    key: "key", label: "Key", defaultDir: "asc",
    get: (s) => (s.dsp_features?.key ? `${s.dsp_features.key} ${s.dsp_features.scale ?? ""}`.trim() : null),
    cellClass: "font-mono text-xs text-ink-2",
  },
  {
    key: "duration", label: "Length", defaultDir: "desc", align: "right",
    get: (s) => s.file_metadata?.duration_seconds ?? null,
    format: fmtDuration,
  },
  {
    key: "bpm", label: "BPM", defaultDir: "desc", align: "right",
    get: (s) => s.dsp_features?.bpm ?? null,
    format: (v) => String(Math.round(v)),
  },
  {
    key: "danceability", label: "Dance", defaultDir: "desc", align: "right",
    get: (s) => s.dsp_features?.danceability ?? null,
    format: score,
  },
  ...MOOD_KEYS.map<Column>((m) => ({
    key: m,
    label: m.charAt(0).toUpperCase() + m.slice(1),
    defaultDir: "desc",
    align: "right",
    get: (s) => s.ml_moods?.[m] ?? null,
    format: score,
  })),
  {
    key: "arousal", label: "Arousal", defaultDir: "desc", align: "right",
    get: (s) => s.ml_profile?.arousal ?? null,
    format: score,
  },
  {
    key: "valence", label: "Valence", defaultDir: "desc", align: "right",
    get: (s) => s.ml_profile?.valence ?? null,
    format: score,
  },
];

interface Props {
  songs: Song[];
  /** Fires whenever the visible row order changes (used to sync the play queue). */
  onVisibleOrderChange?: (ids: string[]) => void;
  /** When set, clicking a row selects that song. */
  onSelect?: (songId: string) => void;
  /** When set (and no onSelect), clicking a row expands a full field dump below it. */
  expandable?: boolean;
}

export function ResultsTable({ songs, onVisibleOrderChange, onSelect, expandable }: Props) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const sorted = useMemo(() => {
    const col = COLUMNS.find((c) => c.key === sortKey);
    if (!col) return songs;
    const dir = sortDir === "asc" ? 1 : -1;
    return [...songs].sort((a, b) => {
      const va = col.get(a);
      const vb = col.get(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1; // missing values always sort last
      if (vb == null) return -1;
      if (typeof va === "string" || typeof vb === "string") {
        return dir * String(va).localeCompare(String(vb));
      }
      return dir * (va - vb);
    });
  }, [songs, sortKey, sortDir]);

  useEffect(() => {
    onVisibleOrderChange?.(sorted.map((s) => s.id));
  }, [sorted, onVisibleOrderChange]);

  // Click cycle per column: default direction → flipped → sorting off.
  const handleHeaderClick = (col: Column) => {
    if (sortKey !== col.key) {
      setSortKey(col.key);
      setSortDir(col.defaultDir);
    } else if (sortDir === col.defaultDir) {
      setSortDir(col.defaultDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(null);
    }
  };

  if (songs.length === 0) {
    return (
      <div className="font-mono text-xs text-ink-3 text-center py-12 border-y border-line">
        No songs match the current filters.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto" style={{ containerType: "inline-size" }}>
      <table className="w-full text-sm whitespace-nowrap">
        <thead>
          <tr className="border-b border-line-strong">
            <th className="w-10 px-2.5 h-8" />
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                className={`px-2.5 h-8 font-normal ${col.align === "right" ? "text-right" : "text-left"}`}
              >
                <button
                  onClick={() => handleHeaderClick(col)}
                  className={`inline-flex items-center gap-1 max-md:h-8 font-mono text-2xs ${
                    sortKey === col.key ? "text-ink" : "text-ink-3 hover:text-ink"
                  }`}
                  title={`Sort by ${col.label}`}
                >
                  {col.label}
                  <span className="w-2 inline-flex text-signal">
                    {sortKey === col.key && (
                      <svg className="w-2 h-2" viewBox="0 0 8 8" fill="currentColor">
                        <path d={sortDir === "asc" ? "M4 1l3.5 5h-7z" : "M4 7L.5 2h7z"} />
                      </svg>
                    )}
                  </span>
                </button>
              </th>
            ))}
            {expandable && !onSelect && <th className="w-8" />}
          </tr>
        </thead>
        <tbody>
          {sorted.map((song) => {
            const isExpanded = expandable && expandedId === song.id;
            const rowClick = onSelect
              ? () => onSelect(song.id)
              : expandable
                ? () => setExpandedId((id) => (id === song.id ? null : song.id))
                : undefined;
            return (
              <Fragment key={song.id}>
                <tr
                  onClick={rowClick}
                  className={`border-b border-line ${rowClick ? "cursor-pointer" : ""} ${isExpanded ? "bg-panel" : "hover:bg-raised/70"}`}
                >
                  <td className="px-2.5 py-1.5">
                    <PlayButton songId={song.id} />
                  </td>
                  {COLUMNS.map((col) => {
                    const v = col.get(song);
                    const text =
                      v == null
                        ? "–"
                        : typeof v === "number"
                          ? col.format
                            ? col.format(v)
                            : String(v)
                          : v;
                    const numeric = col.align === "right";
                    return (
                      <td
                        key={col.key}
                        className={`px-2.5 py-1.5 ${numeric ? "text-right font-mono text-xs text-ink-2 tabular-nums" : "text-left"} ${col.cellClass ?? ""} ${v == null ? "!text-ink-4" : ""}`}
                      >
                        <div className={`truncate ${col.widthClass ?? "max-w-56"}`}>{text}</div>
                      </td>
                    );
                  })}
                  {expandable && !onSelect && (
                    <td className="px-2 py-1.5 text-right">
                      <svg
                        className={`w-3 h-3 inline transition-transform ${isExpanded ? "rotate-180 text-ink-2" : "text-ink-4"}`}
                        fill="none" viewBox="0 0 24 24" stroke="currentColor"
                      >
                        <path strokeLinecap="square" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </td>
                  )}
                </tr>
                {isExpanded && (
                  <tr className="bg-panel border-b border-line">
                    <td colSpan={COLUMNS.length + 2} className="p-0 whitespace-normal">
                      {/* Pinned to the visible part of the horizontally scrolling table */}
                      <div className="sticky left-0 pl-12 pr-4 pt-4 pb-6" style={{ width: "100cqw" }}>
                        <SongDetails song={song} />
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
