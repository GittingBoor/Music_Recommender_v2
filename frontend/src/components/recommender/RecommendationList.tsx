import type { ReactNode } from "react";
import type { Song } from "../../types/song";
import { Link, navigate, recommenderPath, songPath } from "../../router";
import { PlayButton } from "../PlayButton";
import { bpmOf, capitalize, keyOf, rankedMoods, topGenre } from "./songFacts";

/** Delay between two rows of the entrance stagger. */
const STAGGER_MS = 35;

// Phones: rank · play · song · action, with the comparison on a second line.
// lg+: one row per song, the comparison in its own columns.
const ROW_GRID =
  "grid grid-cols-[1.25rem_1.75rem_minmax(0,1fr)_auto] lg:grid-cols-[1.75rem_1.75rem_minmax(0,2fr)_5rem_6.5rem_minmax(0,1fr)_minmax(0,1fr)_8.5rem] items-center gap-x-2 lg:gap-x-4";

interface Props {
  seed: Song;
  recommendations: readonly Song[];
}

/** Ranked nearest neighbours of the seed, each compared with it on a few features. */
export function RecommendationList({ seed, recommendations }: Props) {
  return (
    <div>
      <div className={`${ROW_GRID} hidden lg:grid h-8 border-b border-line-strong t-label`}>
        <span className="text-right">#</span>
        <span />
        <span>Song</span>
        <span className="text-right">BPM</span>
        {/* pl-3 lines the labels up with the values behind the same-as-seed mark */}
        <span className="pl-3">Key</span>
        <span className="pl-3">Genre</span>
        <span className="pl-3">Mood</span>
        <span />
      </div>
      <ol>
        {recommendations.map((song, i) => (
          <RecommendationRow key={song.id} seed={seed} song={song} rank={i + 1} />
        ))}
      </ol>
    </div>
  );
}

interface RowProps {
  seed: Song;
  song: Song;
  rank: number;
}

function RecommendationRow({ seed, song, rank }: RowProps) {
  return (
    <li
      className={`${ROW_GRID} settle gap-y-1 py-2 lg:py-1.5 border-b border-line hover:bg-raised/60`}
      style={{ animationDelay: `${(rank - 1) * STAGGER_MS}ms` }}
    >
      <span className="font-mono text-xs text-ink-3 tabular-nums text-right">{rank}</span>
      <PlayButton songId={song.id} />
      <div className="min-w-0">
        <Link
          to={songPath(song.id)}
          className="block truncate font-medium text-ink hover:underline underline-offset-2"
        >
          {song.title ?? "Unknown"}
        </Link>
        <p className="truncate text-xs text-ink-3">{song.artist ?? "Unknown artist"}</p>
      </div>
      <div className="col-start-3 col-span-2 row-start-2 lg:contents flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-2xs lg:text-xs">
        <BpmCell seed={seed} song={song} />
        <CompareCell label="Key" value={keyOf(song)} same={keyOf(song) === keyOf(seed)} />
        <CompareCell
          label="Genre"
          value={topGenre(song)?.name ?? null}
          same={topGenre(song)?.name === topGenre(seed)?.name}
        />
        <CompareCell
          label="Mood"
          value={rankedMoods(song)[0]?.name ?? null}
          same={rankedMoods(song)[0]?.name === rankedMoods(seed)[0]?.name}
          format={capitalize}
        />
      </div>
      <button
        onClick={() => navigate(recommenderPath(song.id))}
        className="btn col-start-4 row-start-1 lg:col-start-auto lg:row-start-auto lg:justify-self-end"
        title={`Use “${song.title ?? "Unknown"}” as the new seed`}
      >
        <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <path d="M1.5 6h9M6.5 2l4 4-4 4" />
        </svg>
        <span className="max-sm:sr-only">More like this</span>
      </button>
    </li>
  );
}

/** Tiny filled square that marks a value equal to the seed's. */
function SameMark({ same }: { same: boolean }) {
  return same ? (
    <span className="inline-block w-1.5 h-1.5 bg-ink-2 shrink-0" title="Same as the seed" aria-label="same as seed" role="img" />
  ) : (
    // Keeps the column aligned on lg; phones need no placeholder.
    <span className="hidden lg:inline-block w-1.5 h-1.5 shrink-0" aria-hidden="true" />
  );
}

function Cell({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <span className={`flex items-center gap-1.5 min-w-0 ${className}`}>
      <span className="lg:hidden text-ink-4">{label}</span>
      {children}
    </span>
  );
}

function BpmCell({ seed, song }: { seed: Song; song: Song }) {
  const bpm = bpmOf(song);
  const seedBpm = bpmOf(seed);
  const delta = bpm != null && seedBpm != null ? bpm - seedBpm : null;
  return (
    <Cell label="BPM" className="lg:justify-end tabular-nums">
      <span className={bpm == null ? "text-ink-4" : "text-ink-2"}>{bpm ?? "–"}</span>
      {delta != null && (
        <span className="text-ink-3 lg:w-8 lg:text-right" title="Difference to the seed">
          {delta === 0 ? "±0" : delta > 0 ? `+${delta}` : `−${-delta}`}
        </span>
      )}
    </Cell>
  );
}

interface CompareCellProps {
  label: string;
  value: string | null;
  same: boolean;
  format?: (v: string) => string;
}

function CompareCell({ label, value, same, format }: CompareCellProps) {
  const matches = same && value != null;
  return (
    <Cell label={label}>
      <SameMark same={matches} />
      <span className={`truncate ${value == null ? "text-ink-4" : matches ? "text-ink" : "text-ink-3"}`}>
        {value == null ? "–" : format ? format(value) : value}
      </span>
    </Cell>
  );
}
