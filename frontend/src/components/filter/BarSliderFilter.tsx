import { useState } from "react";

export interface BarRow {
  key: string;
  label: string;
  /** Library frequency — rendered as a proportional background bar. */
  count?: number;
  /** Library value distribution (bin counts over 0–1) — rendered instead of the count bar. */
  histogram?: number[];
  /** Per-row accent colour; falls back to the filter's accentColor. */
  color?: string;
}

interface Props {
  title: string;
  rows: BarRow[];
  thresholds: Record<string, number>;
  onChange: (key: string, value: number) => void;
  onReset: () => void;
  enabled: boolean;
  onToggleEnabled: () => void;
  accentColor?: string;
}

export function BarSliderFilter({
  title,
  rows,
  thresholds,
  onChange,
  onReset,
  enabled,
  onToggleEnabled,
  accentColor = "#818cf8",
}: Props) {
  const [open, setOpen] = useState(true);
  const maxCount = Math.max(1, ...rows.map((r) => r.count ?? 0));
  const activeCount = rows.filter((r) => (thresholds[r.key] ?? 0) > 0).length;
  const dimmed = !enabled;

  return (
    <div className="border-b border-gray-800 px-4 py-3 flex flex-col gap-3">
      {/* header */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-1.5 text-xs font-semibold text-gray-400 hover:text-gray-200 uppercase tracking-wider transition-colors"
          aria-expanded={open}
        >
          <svg
            className={`w-3 h-3 transition-transform ${open ? "rotate-90" : ""}`}
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3}
            strokeLinecap="round" strokeLinejoin="round"
          >
            <polyline points="9 6 15 12 9 18" />
          </svg>
          {title}
          {activeCount > 0 && (
            <span className="ml-1 px-1.5 rounded-full bg-violet-500/20 text-violet-300 normal-case tracking-normal">
              {activeCount}
            </span>
          )}
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={onReset}
            className="text-xs text-gray-600 hover:text-gray-300 transition-colors px-2 py-0.5 rounded hover:bg-gray-800"
          >
            Reset
          </button>
          <button
            onClick={onToggleEnabled}
            className={`px-2.5 py-0.5 rounded text-xs font-medium transition-colors border ${
              enabled
                ? "border-violet-500 text-violet-400 bg-violet-500/10"
                : "border-gray-700 text-gray-500 hover:border-gray-500 hover:text-gray-400"
            }`}
          >
            {enabled ? "On" : "Off"}
          </button>
        </div>
      </div>

      {/* rows */}
      {open && (
        <div className={`space-y-2 ${dimmed ? "opacity-50" : ""}`}>
          {rows.map((row) => {
            const thresh = thresholds[row.key] ?? 0;
            const isActive = thresh > 0;
            const color = row.color ?? accentColor;
            return (
              <div key={row.key} className="space-y-0.5">
                <div className="flex items-center justify-between text-xs">
                  <span
                    className="truncate max-w-[160px]"
                    style={{ color: isActive ? color : "#9ca3af" }}
                  >
                    {row.label}
                  </span>
                  <span className="text-gray-600 shrink-0 ml-2">
                    {isActive ? `≥${(thresh * 100).toFixed(0)}%` : row.count != null ? `${row.count}` : "–"}
                  </span>
                </div>
                <div className="relative h-5 bg-gray-800 rounded overflow-hidden">
                  {row.histogram ? (
                    /* background: library distribution, bins below the threshold greyed out */
                    <div className="absolute inset-0 flex items-end gap-px">
                      {(() => {
                        const maxBin = Math.max(1, ...row.histogram);
                        const n = row.histogram.length;
                        return row.histogram.map((c, i) => (
                          <div
                            key={i}
                            className="flex-1"
                            style={{
                              height: `${(c / maxBin) * 100}%`,
                              background: isActive && (i + 1) / n > thresh ? color : "#4b5563",
                              opacity: 0.45,
                              transition: "background 0.2s",
                            }}
                          />
                        ));
                      })()}
                    </div>
                  ) : (
                    /* background: library frequency */
                    <div
                      className="absolute inset-y-0 left-0 rounded"
                      style={{
                        width: `${((row.count ?? 0) / maxCount) * 100}%`,
                        background: isActive ? color : "#374151",
                        opacity: 0.4,
                        transition: "background 0.2s",
                      }}
                    />
                  )}
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.01}
                    value={thresh}
                    disabled={!enabled}
                    onChange={(e) => onChange(row.key, parseFloat(e.target.value))}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-default"
                    aria-label={`${title}: ${row.label} minimum`}
                  />
                  {/* threshold marker */}
                  {isActive && (
                    <div
                      className="absolute inset-y-0 w-0.5 rounded pointer-events-none"
                      style={{
                        left: `${thresh * 100}%`,
                        background: color,
                        opacity: 0.9,
                      }}
                    />
                  )}
                </div>
              </div>
            );
          })}
          {rows.length === 0 && (
            <div className="text-xs text-gray-600">No data.</div>
          )}
        </div>
      )}
    </div>
  );
}
