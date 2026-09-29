import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Song } from "../../types/song";
import { fetchNeighbors } from "../../services/api";
import { setQueue } from "../../audio/player";
import { Link, navigate, recommenderPath, songPath } from "../../router";
import { PlayButton } from "../PlayButton";
import { SongPicker } from "./SongPicker";
import { RecommendationList } from "./RecommendationList";
import { bpmOf, capitalize, keyOf, pct, rankedMoods, topGenre } from "./songFacts";

type NeighborState =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly ids: readonly string[] }
  | { readonly status: "error"; readonly message: string };

/** Result of the last finished request, tagged with the seed it belongs to. */
type Settled = Exclude<NeighborState, { status: "loading" }> & { readonly seedId: string };

/** Loads the seed's neighbour IDs; `retry` refetches after an error. */
function useNeighbors(seedId: string | null): [NeighborState, () => void] {
  const [settled, setSettled] = useState<Settled | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!seedId) return;
    let cancelled = false;
    setSettled(null);
    fetchNeighbors(encodeURIComponent(seedId))
      .then((ids) => { if (!cancelled) setSettled({ status: "ready", ids, seedId }); })
      .catch((e: Error) => { if (!cancelled) setSettled({ status: "error", message: e.message, seedId }); });
    return () => { cancelled = true; };
  }, [seedId, attempt]);

  // A result for the previous seed must never show under the new one.
  const state: NeighborState = settled?.seedId === seedId ? settled : { status: "loading" };
  return [state, () => setAttempt((n) => n + 1)];
}

interface Props {
  songs: Song[];
  /** Song the recommendations are based on (from the URL), null when none is picked. */
  seedId: string | null;
  /** False while another page is shown (the page stays mounted to keep its state). */
  active: boolean;
}

/** Pick one song, get its nearest neighbours over all audio features. */
export function RecommenderPage({ songs, seedId, active }: Props) {
  const seed = useMemo(() => songs.find((s) => s.id === seedId) ?? null, [songs, seedId]);
  const [neighbors, retry] = useNeighbors(seed ? seed.id : null);
  // Phones: the picker is an overlay once a seed is shown.
  const [pickerOpen, setPickerOpen] = useState(false);
  const resultsRef = useRef<HTMLElement>(null);

  const neighborIds = neighbors.status === "ready" ? neighbors.ids : null;
  const recommendations = useMemo<Song[]>(() => {
    if (!neighborIds) return [];
    const byId = new Map(songs.map((s) => [s.id, s]));
    return neighborIds.flatMap((id) => byId.get(id) ?? []);
  }, [songs, neighborIds]);

  useEffect(() => {
    resultsRef.current?.scrollTo({ top: 0 });
  }, [seedId]);

  useRecommenderQueue(songs, seed, recommendations, active);

  const selectSeed = (id: string) => {
    setPickerOpen(false);
    navigate(recommenderPath(id));
  };

  const showPicker = !seedId || pickerOpen;

  return (
    <div className="h-full flex relative">
      <aside
        className={`${showPicker ? "block" : "hidden"} ${seedId ? "absolute inset-0 z-30" : ""} md:static md:z-auto md:block w-full md:w-72 xl:w-80 shrink-0 overflow-y-auto border-r border-line bg-panel`}
      >
        <SongPicker
          songs={songs}
          selectedId={seedId}
          onSelect={selectSeed}
          onClose={seedId ? () => setPickerOpen(false) : undefined}
        />
      </aside>

      <section ref={resultsRef} className={`${seedId ? "block" : "hidden"} md:block flex-1 min-w-0 overflow-y-auto`}>
        {!seedId && <EmptyState />}
        {seedId && !seed && <SeedNotFound />}
        {seed && (
          <div className="max-w-6xl px-3 pt-3 pb-16 md:px-6 md:pt-5 space-y-8">
            <SeedHeader seed={seed} onChangeSeed={() => setPickerOpen(true)} />
            <section aria-labelledby="rec-heading" className="space-y-3">
              <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
                <h3 id="rec-heading" className="t-section">Closest songs</h3>
                <p className="t-label flex items-center gap-1.5">
                  <span className="inline-block w-1.5 h-1.5 bg-ink-2" aria-hidden="true" />
                  same as seed · ranked by distance over all audio features
                </p>
              </div>
              <NeighborResults
                state={neighbors}
                seed={seed}
                recommendations={recommendations}
                onRetry={retry}
              />
            </section>
          </div>
        )}
      </section>
    </div>
  );
}

/**
 * While the page is shown, the play queue is the seed followed by its neighbours;
 * leaving restores the full library. The restore is a layout effect so it runs
 * before the passive effect of SongsPage, which sets its own queue when it becomes active.
 */
function useRecommenderQueue(
  songs: readonly Song[],
  seed: Song | null,
  recommendations: readonly Song[],
  active: boolean,
): void {
  const allSongsRef = useRef(songs);
  allSongsRef.current = songs;

  useLayoutEffect(() => {
    if (!active) setQueue(allSongsRef.current.map((s) => s.id));
  }, [active]);

  useEffect(() => {
    if (!active) return;
    const ids = seed ? [seed, ...recommendations] : allSongsRef.current;
    setQueue(ids.map((s) => s.id));
  }, [active, seed, recommendations]);
}

function SeedHeader({ seed, onChangeSeed }: { seed: Song; onChangeSeed: () => void }) {
  const bpm = bpmOf(seed);
  const key = keyOf(seed);
  const genre = topGenre(seed);
  const [mood, secondMood] = rankedMoods(seed);

  return (
    <header>
      <div className="flex items-start gap-3">
        <PlayButton songId={seed.id} className="mt-1 !w-9 !h-9 border border-line-strong" />
        <div className="min-w-0 flex-1">
          <h2 className="text-2xl md:text-3xl font-semibold text-ink stretch-semi tracking-[-0.02em] leading-[1.05] break-words">
            {seed.title ?? "Unknown"}
          </h2>
          <p className="text-md md:text-lg text-ink-2 mt-1.5 truncate">{seed.artist ?? "Unknown artist"}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 mt-4">
        <button onClick={onChangeSeed} className="btn h-8 md:hidden">Change song</button>
        <Link to={songPath(seed.id)} className="btn h-8">Song details</Link>
      </div>
      <dl className="flex flex-wrap gap-x-10 gap-y-4 border-y border-line-strong mt-5 py-4">
        <Fact label="BPM" value={bpm != null ? String(bpm) : "–"} />
        <Fact label="Key" value={key ?? "–"} />
        <Fact label="Top genre" value={genre?.name ?? "–"} sub={genre ? `${pct(genre.value)} share` : undefined} />
        <Fact
          label="Top mood"
          value={mood ? capitalize(mood.name) : "–"}
          sub={mood ? `${pct(mood.value)}${secondMood ? ` · then ${capitalize(secondMood.name)} ${pct(secondMood.value)}` : ""}` : undefined}
        />
      </dl>
    </header>
  );
}

/** One seed property: label above, value below; wraps with its siblings on narrow screens. */
function Fact({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <dt className="t-label">{label}</dt>
      <dd className="text-xl font-medium text-ink leading-none stretch-condensed tabular-nums mt-2">{value}</dd>
      {sub && <dd className="font-mono text-2xs text-ink-3 mt-1.5">{sub}</dd>}
    </div>
  );
}

interface NeighborResultsProps {
  state: NeighborState;
  seed: Song;
  recommendations: readonly Song[];
  onRetry: () => void;
}

function NeighborResults({ state, seed, recommendations, onRetry }: NeighborResultsProps) {
  switch (state.status) {
    case "loading":
      return (
        <div className="relative border-y border-line py-12 text-center font-mono text-xs text-ink-3">
          <div className="absolute inset-x-0 top-0 h-[2px] overflow-hidden">
            <div className="sweep h-full w-1/4 bg-signal" />
          </div>
          Finding the closest songs…
        </div>
      );
    case "error":
      return (
        <div className="border-y border-line py-10 flex flex-col items-center gap-3 font-mono text-xs text-center">
          <p className="text-bad">
            Could not load recommendations for “{seed.title ?? "Unknown"}” ({state.message}).
          </p>
          <p className="text-ink-3">Check that the backend is running, then try again.</p>
          <button onClick={onRetry} className="btn h-8 font-sans">Try again</button>
        </div>
      );
    case "ready":
      return recommendations.length === 0 ? (
        <p className="border-y border-line py-12 text-center font-mono text-xs text-ink-3">
          No other songs in the library to compare with yet.
        </p>
      ) : (
        <RecommendationList seed={seed} recommendations={recommendations} />
      );
  }
}

function EmptyState() {
  return (
    <div className="h-full flex items-center justify-center px-6">
      <div className="max-w-sm space-y-2">
        <h2 className="text-xl font-semibold text-ink stretch-semi tracking-[-0.01em]">Start from one song</h2>
        <p className="text-ink-2">
          Pick a song on the left. The ten songs closest to it across all audio features
          appear here, closest first. Play any of them, or follow one to keep exploring.
        </p>
      </div>
    </div>
  );
}

function SeedNotFound() {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-3 font-mono text-xs text-ink-3 px-6 text-center">
      <p>Song not found. It may have been removed from the library.</p>
      <Link to="/recommender" className="btn-quiet">Pick another song</Link>
    </div>
  );
}
