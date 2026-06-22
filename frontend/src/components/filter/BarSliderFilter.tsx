export interface BarRow {
  key: string;
  label: string;
  count: number;
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
  const maxCount = Math.max(1, ...rows.map((r) => r.count));
  const dimmed = !enabled;

  return (
    <div className={`bg-gray-900 border border-gray-800 rounded-lg p-4 flex flex-col gap-3 ${dimmed ? "opacity-50" : ""}`}>
      {/* header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{title}</span>
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
      <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
        {rows.map((row) => {
          const thresh = thresholds[row.key] ?? 0;
          const barWidth = (row.count / maxCount) * 100;
          const isActive = thresh > 0;
          return (
            <div key={row.key} className="space-y-0.5">
              <div className="flex items-center justify-between text-xs">
                <span
                  className="truncate max-w-[160px]"
                  style={{ color: isActive ? accentColor : "#9ca3af" }}
                >
                  {row.label}
                </span>
                <span className="text-gray-600 shrink-0 ml-2">
                  {isActive ? `≥${(thresh * 100).toFixed(0)}%` : `${row.count}`}
                </span>
              </div>
              {/* background bar (library frequency) */}
              <div className="relative h-5 bg-gray-800 rounded overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0 rounded"
                  style={{
                    width: `${barWidth}%`,
                    background: isActive ? accentColor : "#374151",
                    opacity: 0.4,
                    transition: "background 0.2s",
                  }}
                />
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={thresh}
                  disabled={!enabled}
                  onChange={(e) => onChange(row.key, parseFloat(e.target.value))}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-default"
                />
                {/* threshold marker */}
                {thresh > 0 && (
                  <div
                    className="absolute inset-y-0 w-0.5 rounded"
                    style={{
                      left: `${thresh * 100}%`,
                      background: accentColor,
                      opacity: 0.9,
                    }}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
