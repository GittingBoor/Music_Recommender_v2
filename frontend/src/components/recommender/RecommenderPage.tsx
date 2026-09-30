import type { Song } from "../../types/song";
import { Link, NEIGHBORS_PATH, recommenderPath } from "../../router";
import { NeighborsSection } from "./NeighborsSection";

export type RecommenderMethod = "neighbors";

/** Sub-tabs in display order; each recommendation method is its own URL. */
export const RECOMMENDER_METHODS: { id: RecommenderMethod; label: string; path: string }[] = [
  { id: "neighbors", label: "Nearest Neighbours", path: NEIGHBORS_PATH },
];

interface Props {
  songs: Song[];
  method: RecommenderMethod;
  /** Song the recommendations are based on (from the URL), null when none is picked. */
  seedId: string | null;
  /** False while another page is shown (the page stays mounted to keep its state). */
  active: boolean;
}

export function RecommenderPage({ songs, method, seedId, active }: Props) {
  return (
    <div className="h-full flex flex-col overflow-hidden">
      <nav className="flex-shrink-0 h-10 border-b border-line px-3 md:px-6 flex items-stretch gap-4 md:gap-6 overflow-x-auto no-scrollbar">
        {RECOMMENDER_METHODS.map((m) => (
          <Link
            key={m.id}
            // The neighbours tab leads back to the seed that is loaded.
            to={m.id === "neighbors" && seedId ? recommenderPath(seedId) : m.path}
            aria-current={method === m.id ? "page" : undefined}
            className="subtab shrink-0 whitespace-nowrap"
          >
            {m.label}
          </Link>
        ))}
      </nav>

      <div className="flex-1 min-h-0">
        {method === "neighbors" && <NeighborsSection songs={songs} seedId={seedId} active={active} />}
      </div>
    </div>
  );
}
