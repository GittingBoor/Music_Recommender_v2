import type { RadarAxis } from "./featureConfig";
import { COLOR, SERIES } from "../../theme";

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
  /** Normalised values of the song in the player, null when nothing is loaded. */
  current: Record<string, number> | null;
  enabled: boolean;
}

/** Colour of the now-playing outline — a series hue, distinct from the signal-coloured filter. */
export const CURRENT_SONG_COLOR = SERIES[0];

/** Read-only radar: visualises the filter thresholds set in the sidebar
 *  against the average profile of the songs that pass them and the song
 *  that is playing. Axes with an active threshold are set in the signal
 *  colour, like their slider rows. */
export function RadarChart({
  title,
  axes,
  thresholds,
  profile,
  current,
  enabled,
}: Props) {
  const n = axes.length;
  const polyColor = enabled ? COLOR.signal : COLOR.ink4;

  const toPoints = (values: Record<string, number>) =>
    axes
      .map((ax, i) => {
        const pt = axisPoint(i, n, values[ax.key] ?? 0);
        return `${pt.x},${pt.y}`;
      })
      .join(" ");

  const hasProfile = axes.some((ax) => profile[ax.key] != null);
  const currentValues = current && axes.some((ax) => current[ax.key] != null) ? current : null;

  return (
    <div className={`flex flex-col gap-1 pb-4 border-b border-line last:border-b-0 ${enabled ? "" : "opacity-40"}`}>
      <span className="text-xs font-semibold text-ink">{title}</span>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-[82%] max-w-[210px] mx-auto overflow-visible">
        {GRID_LEVELS.map((lvl) => (
          <polygon
            key={lvl}
            points={axes.map((_, i) => { const p = axisPoint(i, n, lvl); return `${p.x},${p.y}`; }).join(" ")}
            fill="none"
            stroke={COLOR.line}
            strokeWidth={1}
          />
        ))}
        {axes.map((_, i) => {
          const pt = axisPoint(i, n, 1);
          return <line key={i} x1={CX} y1={CY} x2={pt.x} y2={pt.y} stroke={COLOR.line} strokeWidth={1} />;
        })}
        {axes.map((ax, i) => {
          const angle = axisAngle(i, n);
          const lx = CX + LABEL_R * Math.cos(angle);
          const ly = CY + LABEL_R * Math.sin(angle);
          const active = (thresholds[ax.key] ?? 0) > 0;
          return (
            <text
              key={ax.key}
              x={lx} y={ly}
              textAnchor={textAnchor(Math.cos(angle))}
              dominantBaseline="central"
              fill={active ? COLOR.signal : COLOR.ink3}
              fontSize={8.5}
            >
              {ax.label}
            </text>
          );
        })}

        {/* average profile of the filtered songs */}
        {hasProfile && (
          <polygon
            points={toPoints(profile)}
            fill={COLOR.ink}
            fillOpacity={0.05}
            stroke={COLOR.ink}
            strokeOpacity={0.6}
            strokeWidth={1}
            strokeDasharray="3 2"
          />
        )}

        {/* filter thresholds */}
        <polygon
          points={toPoints(thresholds)}
          fill={polyColor}
          fillOpacity={0.18}
          stroke={polyColor}
          strokeWidth={1.5}
        />
        {axes.map((ax, i) => {
          const thresh = thresholds[ax.key] ?? 0;
          if (thresh === 0) return null;
          const pt = axisPoint(i, n, thresh);
          return (
            <rect
              key={ax.key}
              x={pt.x - 2.5} y={pt.y - 2.5} width={5} height={5}
              fill={COLOR.signal}
            />
          );
        })}

        {/* song in the player — on top so it stays readable over the filter */}
        {currentValues && (
          <>
            <polygon
              points={toPoints(currentValues)}
              fill="none"
              stroke={CURRENT_SONG_COLOR}
              strokeWidth={1.5}
              strokeLinejoin="round"
            />
            {axes.map((ax, i) => {
              const v = currentValues[ax.key];
              if (v == null) return null;
              const pt = axisPoint(i, n, v);
              return <circle key={ax.key} cx={pt.x} cy={pt.y} r={2} fill={CURRENT_SONG_COLOR} />;
            })}
          </>
        )}
      </svg>
    </div>
  );
}
