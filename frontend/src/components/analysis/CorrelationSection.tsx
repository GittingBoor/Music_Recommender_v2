import { useEffect, useRef, useState } from "react";
import { fetchCorrelations } from "../../services/api";
import type { CorrelationResponse } from "../../types/analysis";
import { COLOR } from "../../theme";

// Diverging scale: neutral grey at 0, blue arm for positive, red arm for negative.
const MID = [44, 42, 39];      // #2c2a27
const POS = [57, 135, 229];    // #3987e5
const NEG = [230, 103, 103];   // #e66767

function corrToColor(v: number | null): string {
  if (v === null) return COLOR.panel;
  const c = Math.max(-1, Math.min(1, v));
  const pole = c >= 0 ? POS : NEG;
  const t = Math.abs(c);
  const [r, g, b] = MID.map((m, i) => Math.round(m + t * (pole[i] - m)));
  return `rgb(${r},${g},${b})`;
}

const FEATURE_LABELS: Record<string, string> = {
  bpm: "BPM", beat_confidence: "Beat Conf.", danceability: "Danceability",
  onset_rate: "Onset Rate", key_strength: "Key Strength",
  chord_strength: "Chord Strength", chord_change_rate: "Chord Chg Rate",
  lufs: "LUFS", loudness_range: "Loudness Range", dynamic_complexity: "Dyn. Complexity",
  loudness_db: "Loudness dB", spectral_centroid: "Spectral Centr.",
  spectral_rolloff: "Spectral Roll.", spectral_flux: "Spectral Flux",
  zero_crossing_rate: "ZCR", dissonance: "Dissonance",
  niche_score: "Niche Score", mainstream: "Mainstream", background: "Background",
  active: "Active", instrumental: "Instrumental", vocal: "Vocal",
  female: "Female", male: "Male", arousal: "Arousal", valence: "Valence",
  happy: "Happy", sad: "Sad", aggressive: "Aggressive", party: "Party",
  relaxed: "Relaxed", acoustic: "Acoustic", electronic: "Electronic",
  playcount: "Playcount", listeners: "Listeners",
};

interface TooltipState { x: number; y: number; i: number; j: number; }

export function CorrelationSection() {
  const [data, setData] = useState<CorrelationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchCorrelations()
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 font-mono text-xs text-ink-3">
        Computing correlations…
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-center justify-center h-64 font-mono text-xs text-bad">
        Error: {error}
      </div>
    );
  }
  if (!data || data.features.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 font-mono text-xs text-ink-3">
        Not enough data for correlations.
      </div>
    );
  }

  const { features, matrix } = data;
  const n = features.length;
  const CELL = 24;
  const LABEL_W = 130;
  const LABEL_H = 130;
  const PADDING_R = 90;   // extra space for rotated last X-label
  const svgW = LABEL_W + n * CELL + PADDING_R;
  const svgH = LABEL_H + n * CELL;

  return (
    <div className="max-w-7xl mx-auto px-4 pt-4 pb-16 md:px-6 md:pt-6">
      <div className="flex items-end justify-between gap-4 md:gap-6 flex-wrap pb-4 border-b border-line-strong">
        <div>
          <h2 className="t-section">
            Pearson Correlation Matrix
          </h2>
          <p className="text-xs text-ink-3 mt-1.5">
            Hover or tap cells to see the correlation value. Blue = positive, Red = negative.
          </p>
        </div>

        {/* Colour scale */}
        <div className="flex items-center gap-2.5 w-full sm:w-64">
          <span className="font-mono text-2xs text-ink-3">−1.0</span>
          <div
            className="h-2 flex-1"
            style={{
              background: `linear-gradient(to right, ${corrToColor(-1)}, ${corrToColor(0)}, ${corrToColor(1)})`,
            }}
          />
          <span className="font-mono text-2xs text-ink-3">+1.0</span>
        </div>
      </div>

      <div className="overflow-auto pt-6" ref={containerRef}>
        <svg width={svgW} height={svgH} style={{ display: "block", margin: "0 auto" }}>
          {/* X-axis labels (rotated -45°) */}
          {features.map((f, i) => (
            <text
              key={`xlabel-${i}`}
              x={LABEL_W + i * CELL + CELL / 2}
              y={LABEL_H - 6}
              textAnchor="start"
              fontSize={9}
              fill={COLOR.ink3}
              transform={`rotate(-45 ${LABEL_W + i * CELL + CELL / 2} ${LABEL_H - 6})`}
            >
              {FEATURE_LABELS[f] ?? f}
            </text>
          ))}

          {/* Y-axis labels */}
          {features.map((f, i) => (
            <text
              key={`ylabel-${i}`}
              x={LABEL_W - 6}
              y={LABEL_H + i * CELL + CELL / 2 + 3.5}
              textAnchor="end"
              fontSize={9}
              fill={COLOR.ink3}
            >
              {FEATURE_LABELS[f] ?? f}
            </text>
          ))}

          {/* Cells */}
          {matrix.map((row, i) =>
            row.map((val, j) => {
              const isHovered = tooltip?.i === i && tooltip?.j === j;
              return (
                <g key={`cell-${i}-${j}`}>
                  <rect
                    x={LABEL_W + j * CELL}
                    y={LABEL_H + i * CELL}
                    width={CELL}
                    height={CELL}
                    fill={corrToColor(val)}
                    stroke={isHovered ? COLOR.ink : COLOR.ground}
                    strokeWidth={isHovered ? 1.5 : 1}
                    style={{ cursor: "crosshair" }}
                    onMouseMove={(e) => setTooltip({ x: e.clientX, y: e.clientY, i, j })}
                    onClick={(e) => setTooltip({ x: e.clientX, y: e.clientY, i, j })}
                    onMouseLeave={() => setTooltip(null)}
                  />
                  {i === j && (
                    <text
                      x={LABEL_W + j * CELL + CELL / 2}
                      y={LABEL_H + i * CELL + CELL / 2 + 3}
                      textAnchor="middle"
                      fontSize={7}
                      fill="rgba(237,233,225,0.5)"
                      pointerEvents="none"
                    >
                      1.0
                    </text>
                  )}
                  {i !== j && val !== null && Math.abs(val) > 0.6 && (
                    <text
                      x={LABEL_W + j * CELL + CELL / 2}
                      y={LABEL_H + i * CELL + CELL / 2 + 3}
                      textAnchor="middle"
                      fontSize={7}
                      fill="rgba(237,233,225,0.9)"
                      pointerEvents="none"
                    >
                      {val.toFixed(2)}
                    </text>
                  )}
                </g>
              );
            })
          )}
        </svg>

      </div>

      {/* Fixed tooltip */}
      {tooltip && (
        <div
          className="fixed pointer-events-none z-50 bg-raised border border-line-strong rounded-sm px-2.5 py-2 text-xs"
          style={{ left: Math.max(8, Math.min(tooltip.x + 14, window.innerWidth - 200)), top: tooltip.y - 10 }}
        >
          <p className="text-ink">
            {FEATURE_LABELS[features[tooltip.j]] ?? features[tooltip.j]}
          </p>
          <p className="text-ink">
            × {FEATURE_LABELS[features[tooltip.i]] ?? features[tooltip.i]}
          </p>
          <p
            className="font-mono font-medium text-sm mt-1"
            style={{
              color:
                matrix[tooltip.i][tooltip.j] == null
                  ? COLOR.ink3
                  : matrix[tooltip.i][tooltip.j]! > 0
                  ? "#6fa8ec"
                  : "#ef8a8a",
            }}
          >
            {matrix[tooltip.i][tooltip.j]?.toFixed(3) ?? "–"}
          </p>
        </div>
      )}
    </div>
  );
}
