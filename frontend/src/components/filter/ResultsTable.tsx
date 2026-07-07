import { useEffect, useMemo, useState } from "react";
import type { Song } from "../../types/song";
import { PlayButton } from "../PlayButton";

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
    cellClass: "font-medium text-white",
  },
  {
    key: "artist", label: "Artist", defaultDir: "asc",
    get: (s) => s.artist,
    cellClass: "text-gray-400",
  },
  {
    key: "key", label: "Key", defaultDir: "asc",
    get: (s) => (s.dsp_features?.key ? `${s.dsp_features.key} ${s.dsp_features.scale ?? ""}`.trim() : null),
    cellClass: "font-mono text-gray-400",
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
}

export function ResultsTable({ songs, onVisibleOrderChange }: Props) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("desc");

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
      <div className="text-gray-600 text-sm text-center py-12 border border-dashed border-gray-800 rounded-lg">
        No songs match the current filters.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full text-sm whitespace-nowrap">
        <thead>
          <tr className="bg-gray-900/60">
            <th className="w-12 px-3 py-2" />
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                className={`px-3 py-2 ${col.align === "right" ? "text-right" : "text-left"}`}
              >
                <button
                  onClick={() => handleHeaderClick(col)}
                  className={`inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider transition-colors ${
                    sortKey === col.key ? "text-violet-400" : "text-gray-500 hover:text-gray-200"
                  }`}
                  title={`Sort by ${col.label}`}
                >
                  {col.label}
                  <span className="w-3 inline-block text-[0.6rem]">
                    {sortKey === col.key ? (sortDir === "asc" ? "▲" : "▼") : ""}
                  </span>
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((song) => (
            <tr
              key={song.id}
              className="border-t border-gray-800 hover:bg-gray-800/60 transition-colors"
            >
              <td className="px-3 py-1.5">
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
                    className={`px-3 py-1.5 ${numeric ? "text-right font-mono text-gray-300" : "text-left"} ${col.cellClass ?? ""}`}
                  >
                    <div className="truncate max-w-56">{text}</div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
