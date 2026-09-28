import type { Song } from "../../types/song";
import { Link } from "../../router";
import { OverviewSection } from "./OverviewSection";
import { UmapView } from "./UmapView";
import { CorrelationSection } from "./CorrelationSection";
import { TimeseriesSection } from "./TimeseriesSection";

export type AnalysisSection = "overview" | "umap" | "correlations" | "timeseries";

/** Sub-tabs in display order; each one is its own URL (overview = /analysis). */
export const ANALYSIS_SECTIONS: { id: AnalysisSection; label: string; path: string }[] = [
  { id: "overview",      label: "Library Overview", path: "/analysis" },
  { id: "umap",          label: "UMAP",             path: "/analysis/umap" },
  { id: "correlations",  label: "Correlations",     path: "/analysis/correlations" },
  { id: "timeseries",    label: "Timeseries",       path: "/analysis/timeseries" },
];

interface Props {
  songs: Song[];
  section: AnalysisSection;
}

export function AnalysisPage({ songs, section }: Props) {
  return (
    <div className="h-full flex flex-col overflow-hidden">
      <nav className="flex-shrink-0 h-10 border-b border-line px-3 md:px-6 flex items-stretch gap-4 md:gap-6 overflow-x-auto no-scrollbar">
        {ANALYSIS_SECTIONS.map((s) => (
          <Link
            key={s.id}
            to={s.path}
            aria-current={section === s.id ? "page" : undefined}
            className="subtab shrink-0 whitespace-nowrap"
          >
            {s.label}
          </Link>
        ))}
      </nav>

      {/* The UMAP fills the area and handles its own scrolling. */}
      <div className={`flex-1 min-h-0 ${section === "umap" ? "overflow-hidden" : "overflow-y-auto"}`}>
        {section === "overview"     && <OverviewSection songs={songs} />}
        {section === "umap"         && <UmapView songs={songs} />}
        {section === "correlations" && <CorrelationSection />}
        {section === "timeseries"   && <TimeseriesSection songs={songs} />}
      </div>
    </div>
  );
}
