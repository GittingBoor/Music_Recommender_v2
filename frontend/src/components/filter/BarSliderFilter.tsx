import { useState } from "react";
import { COLOR } from "../../theme";

export interface BarRow {
  key: string;
  label: string;
  /** Library frequency — rendered as a proportional background bar. */
  count?: number;
  /** Library value distribution (bin counts over 0–1) — rendered instead of the count bar. */
  histogram?: number[];
}

interface Props {
  title: string;
  rows: BarRow[];
  thresholds: Record<string, number>;
  onChange: (key: string, value: number) => void;
  onReset: () => void;
  enabled: boolean;
  onToggleEnabled: () => void;
}

export function BarSliderFilter({
  title,
  rows,
  thresholds,
  onChange,
  onReset,
  enabled,
  onToggleEnabled,
}: Props) {
  const [open, setOpen] = useState(true);
  const maxCount = Math.max(1, ...rows.map((r) => r.count ?? 0));
  const activeCount = rows.filter((r) => (thresholds[r.key] ?? 0) > 0).length;
  const dimmed = !enabled;

  return (
    <div className="border-b border-line px-5 py-3.5 flex flex-col gap-3">
      {/* header */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-2 text-sm font-semibold text-ink"
          aria-expanded={open}
        >
          <svg
            className={`w-2.5 h-2.5 text-ink-3 transition-transform ${open ? "rotate-90" : ""}`}
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3.5}
            strokeLinecap="square"
          >
            <polyline points="9 5 16 12 9 19" />
          </svg>
          {title}
          {activeCount > 0 && (
            <span className="font-mono text-2xs font-medium text-signal">
              {activeCount}
            </span>
          )}
        </button>
        <div className="flex items-center gap-3">
          <button
            onClick={onReset}
            className="btn-quiet relative max-md:after:absolute max-md:after:-inset-x-1 max-md:after:-inset-y-2.5 max-md:after:content-['']"
          >
            Reset
          </button>
          <button
            onClick={onToggleEnabled}
            aria-pressed={enabled}
            className={`relative h-5 w-8 rounded-sm font-mono max-md:after:absolute max-md:after:-inset-x-1 max-md:after:-inset-y-2.5 max-md:after:content-[''] text-2xs border ${
              enabled
                ? "border-signal/70 text-signal"
                : "border-line-strong text-ink-4 hover:text-ink-2"
            }`}
          >
            {enabled ? "On" : "Off"}
          </button>
        </div>
      </div>

      {/* rows */}
      {open && (
        <div className={`space-y-2 ${dimmed ? "opacity-40" : ""}`}>
          {rows.map((row) => {
            const thresh = thresholds[row.key] ?? 0;
            const isActive = thresh > 0;
            return (
              <div key={row.key} className="space-y-1">
                <div className="flex items-baseline justify-between text-xs">
                  <span className={`truncate max-w-[170px] ${isActive ? "text-ink" : "text-ink-2"}`}>
                    {row.label}
                  </span>
                  <span className={`font-mono text-2xs shrink-0 ml-2 tabular-nums ${isActive ? "text-signal" : "text-ink-4"}`}>
                    {isActive ? `≥${(thresh * 100).toFixed(0)}%` : row.count != null ? `${row.count}` : "–"}
                  </span>
                </div>
                <div className="relative h-5 bg-raised">
                  {row.histogram ? (
                    /* background: library distribution, bins below the threshold recede */
                    <div className="absolute inset-0 flex items-end gap-px">
                      {(() => {
                        const maxBin = Math.max(1, ...row.histogram);
                        const n = row.histogram.length;
                        return row.histogram.map((c, i) => {
                          const passes = isActive && (i + 1) / n > thresh;
                          return (
                            <div
                              key={i}
                              className="flex-1"
                              style={{
                                height: `${(c / maxBin) * 100}%`,
                                background: passes ? COLOR.signal : COLOR.ink4,
                                opacity: passes ? 0.75 : isActive ? 0.3 : 0.55,
                                transition: "background 0.2s, opacity 0.2s",
                              }}
                            />
                          );
                        });
                      })()}
                    </div>
                  ) : (
                    /* background: library frequency */
                    <div
                      className="absolute inset-y-0 left-0"
                      style={{
                        width: `${((row.count ?? 0) / maxCount) * 100}%`,
                        background: isActive ? COLOR.signal : COLOR.ink4,
                        opacity: isActive ? 0.45 : 0.4,
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
                      className="absolute inset-y-0 w-[2px] pointer-events-none bg-signal"
                      style={{ left: `${thresh * 100}%` }}
                    />
                  )}
                </div>
              </div>
            );
          })}
          {rows.length === 0 && (
            <div className="font-mono text-2xs text-ink-3">No data.</div>
          )}
        </div>
      )}
    </div>
  );
}
