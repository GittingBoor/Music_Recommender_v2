import type { RadarAxis } from "./featureConfig";

const W = 200;
const H = 200;
const CX = W / 2;
const CY = H / 2;
const R  = 70;
const LABEL_R = R + 14;
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
  /** Filter thresholds (0–1 per axis) — drawn as the filled polygon. */
  thresholds: Record<string, number>;
  /** Mean normalised value per axis over the currently filtered songs. */
  profile: Record<string, number>;
  enabled: boolean;
  axisColors?: Record<string, string>;
}

/** Read-only radar: visualises the filter thresholds set in the sidebar
 *  against the average profile of the songs that pass them. */
export function RadarChart({
  title,
  axes,
  thresholds,
  profile,
  enabled,
  axisColors = {},
}: Props) {
  const n = axes.length;
  const polyColor = enabled ? "#818cf8" : "#374151";

  const toPoints = (values: Record<string, number>) =>
    axes
      .map((ax, i) => {
        const pt = axisPoint(i, n, values[ax.key] ?? 0);
        return `${pt.x},${pt.y}`;
      })
      .join(" ");

  const hasProfile = axes.some((ax) => profile[ax.key] != null);

  return (
    <div className={`bg-gray-900 border border-gray-800 rounded-lg p-3 flex flex-col gap-1 ${enabled ? "" : "opacity-50"}`}>
      <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{title}</span>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[220px] mx-auto overflow-visible">
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

        {/* average profile of the filtered songs */}
        {hasProfile && (
          <polygon
            points={toPoints(profile)}
            fill="#e5e7eb"
            fillOpacity={0.06}
            stroke="#e5e7eb"
            strokeOpacity={0.6}
            strokeWidth={1}
            strokeDasharray="3 2"
          />
        )}

        {/* filter thresholds */}
        <polygon
          points={toPoints(thresholds)}
          fill={polyColor}
          fillOpacity={0.2}
          stroke={polyColor}
          strokeWidth={1.5}
        />
        {axes.map((ax, i) => {
          const thresh = thresholds[ax.key] ?? 0;
          if (thresh === 0) return null;
          const pt = axisPoint(i, n, thresh);
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
    </div>
  );
}
