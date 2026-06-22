import type { RadarAxis, AxisStatsMap } from "./featureConfig";

const W = 200;
const H = 200;
const CX = W / 2;
const CY = H / 2;
const R  = 78;
const LABEL_R = R + 18;
const GRID_LEVELS = [0.25, 0.5, 0.75, 1.0];

function axisAngle(i: number, n: number): number {
  return ((-90 + (i * 360) / n) * Math.PI) / 180;
}

function axisPoint(i: number, n: number, frac: number) {
  const a = axisAngle(i, n);
  return { x: CX + frac * R * Math.cos(a), y: CY + frac * R * Math.sin(a) };
}

function textAnchor(cosA: number): "start" | "middle" | "end" {
  if (cosA > 0.3) return "start";
  if (cosA < -0.3) return "end";
  return "middle";
}

interface Props {
  title: string;
  axes: RadarAxis[];
  stats: AxisStatsMap;
  thresholds: Record<string, number>;
  onChange: (key: string, value: number) => void;
  onReset: () => void;
  enabled: boolean;
  onToggleEnabled: () => void;
  axisColors?: Record<string, string>;
}

export function RadarFilter({
  title,
  axes,
  stats: _stats,
  thresholds,
  onChange,
  onReset,
  enabled,
  onToggleEnabled,
  axisColors = {},
}: Props) {
  const n = axes.length;
  const dimmed = !enabled;
  const polyColor = enabled ? "#818cf8" : "#374151";

  const polygonPts = axes
    .map((ax, i) => {
      const pt = axisPoint(i, n, thresholds[ax.key] ?? 0);
      return `${pt.x},${pt.y}`;
    })
    .join(" ");

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

      {/* radar — visualization only */}
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[200px] mx-auto">
        {GRID_LEVELS.map((lvl) => (
          <polygon
            key={lvl}
            points={axes.map((_, i) => { const p = axisPoint(i, n, lvl); return `${p.x},${p.y}`; }).join(" ")}
            fill="none"
            stroke="#1f2937"
            strokeWidth={1}
          />
        ))}
        {axes.map((_, i) => {
          const pt = axisPoint(i, n, 1);
          return <line key={i} x1={CX} y1={CY} x2={pt.x} y2={pt.y} stroke="#1f2937" strokeWidth={1} />;
        })}
        {axes.map((ax, i) => {
          const angle = axisAngle(i, n);
          const lx = CX + LABEL_R * Math.cos(angle);
          const ly = CY + LABEL_R * Math.sin(angle);
          return (
            <text
              key={ax.key}
              x={lx} y={ly}
              textAnchor={textAnchor(Math.cos(angle))}
              dominantBaseline="central"
              fill={axisColors[ax.key] ?? "#9ca3af"}
              fontSize={8.5}
              fontWeight={600}
            >
              {ax.label}
            </text>
          );
        })}
        <polygon
          points={polygonPts}
          fill={polyColor}
          fillOpacity={0.2}
          stroke={polyColor}
          strokeWidth={1.5}
        />
        {/* dot per axis */}
        {axes.map((ax, i) => {
          const thresh = thresholds[ax.key] ?? 0;
          const pt = axisPoint(i, n, thresh);
          if (thresh === 0) return null;
          return (
            <circle
              key={ax.key}
              cx={pt.x} cy={pt.y} r={3}
              fill={axisColors[ax.key] ?? "#818cf8"}
              fillOpacity={0.9}
            />
          );
        })}
      </svg>

      {/* sliders */}
      <div className="space-y-1.5">
        {axes.map((ax) => {
          const thresh = thresholds[ax.key] ?? 0;
          const color = axisColors[ax.key] ?? "#818cf8";
          return (
            <div key={ax.key} className="flex items-center gap-2">
              <span
                className="text-xs w-20 shrink-0 truncate"
                style={{ color: thresh > 0 ? color : "#6b7280" }}
              >
                {ax.label}
              </span>
              <div className="relative flex-1 h-4">
                <div className="absolute inset-y-1.5 left-0 right-0 bg-gray-800 rounded" />
                {thresh > 0 && (
                  <div
                    className="absolute inset-y-1.5 left-0 rounded"
                    style={{ width: `${thresh * 100}%`, background: color, opacity: 0.5 }}
                  />
                )}
                <input
                  type="range"
                  min={0} max={1} step={0.01}
                  value={thresh}
                  disabled={!enabled}
                  onChange={(e) => onChange(ax.key, parseFloat(e.target.value))}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-default"
                />
              </div>
              <span className="text-xs font-mono text-gray-600 w-8 text-right shrink-0">
                {thresh > 0 ? `${(thresh * 100).toFixed(0)}%` : "–"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
