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
      <div className="flex-shrink-0 border-b border-gray-800 px-6 flex items-center gap-1 pt-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-sm font-medium rounded-t transition-colors border-b-2 -mb-px ${
              tab === t.id
                ? "border-violet-500 text-violet-400 bg-gray-900"
                : "border-transparent text-gray-500 hover:text-gray-300 hover:border-gray-600"
            }`}
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
