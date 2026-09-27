import { useState } from "react";
import type { Song } from "../../types/song";
import { OverviewSection } from "./OverviewSection";
import { CorrelationSection } from "./CorrelationSection";
import { TimeseriesSection } from "./TimeseriesSection";
import { SongDetailSection } from "./SongDetailSection";

type AnalysisTab = "overview" | "correlations" | "timeseries" | "song";

const TABS: { id: AnalysisTab; label: string }[] = [
  { id: "overview",      label: "Library Overview" },
  { id: "correlations",  label: "Correlations" },
  { id: "timeseries",    label: "Timeseries" },
  { id: "song",          label: "Song Detail" },
];

interface Props {
  songs: Song[];
}

export function AnalysisPage({ songs }: Props) {
  const [tab, setTab] = useState<AnalysisTab>("overview");

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-shrink-0 h-10 border-b border-line px-3 md:px-6 flex items-stretch gap-4 md:gap-6 overflow-x-auto no-scrollbar">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            aria-current={tab === t.id ? "page" : undefined}
            className="subtab shrink-0 whitespace-nowrap"
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto">
        {tab === "overview"     && <OverviewSection songs={songs} />}
        {tab === "correlations" && <CorrelationSection />}
        {tab === "timeseries"   && <TimeseriesSection songs={songs} />}
        {tab === "song"         && <SongDetailSection songs={songs} />}
      </div>
    </div>
  );
}
