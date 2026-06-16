import { useEffect, useRef, useState } from "react";
import { fetchCorrelations } from "../../services/api";
import type { CorrelationResponse } from "../../types/analysis";

function corrToColor(v: number | null): string {
  if (v === null) return "#111827";
  const c = Math.max(-1, Math.min(1, v));
  if (c >= 0) {
    const t = c;
    const r = Math.round(31  + t * (59  - 31));
    const g = Math.round(41  + t * (130 - 41));
    const b = Math.round(55  + t * (246 - 55));
    return `rgb(${r},${g},${b})`;
  } else {
    const t = -c;
    const r = Math.round(31  + t * (239 - 31));
    const g = Math.round(41  + t * (68  - 41));
    const b = Math.round(55  + t * (68  - 55));
    return `rgb(${r},${g},${b})`;
  }
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
      <div className="flex items-center justify-center h-64 text-gray-500 text-sm">
        Computing correlations…
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400 text-sm">
        Error: {error}
      </div>
    );
  }
  if (!data || data.features.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-600 text-sm">
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
    <div className="max-w-7xl mx-auto px-6 py-6">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest">
          Pearson Correlation Matrix
        </h2>
        <p className="text-xs text-gray-600 mt-1">
          Hover cells to see the correlation value. Blue = positive, Red = negative.
        </p>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 overflow-auto" ref={containerRef}>
        <svg width={svgW} height={svgH} style={{ display: "block", margin: "0 auto" }}>
          {/* X-axis labels (rotated -45°) */}
          {features.map((f, i) => (
            <text
              key={`xlabel-${i}`}
              x={LABEL_W + i * CELL + CELL / 2}
              y={LABEL_H - 6}
              textAnchor="start"
              fontSize={9}
              fill="#6b7280"
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
              fill="#6b7280"
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
                    stroke={isHovered ? "#f3f4f6" : "#0a0f1a"}
                    strokeWidth={isHovered ? 1.5 : 0.5}
                    style={{ cursor: "crosshair" }}
                    onMouseMove={(e) => setTooltip({ x: e.clientX, y: e.clientY, i, j })}
                    onMouseLeave={() => setTooltip(null)}
                  />
                  {i === j && (
                    <text
                      x={LABEL_W + j * CELL + CELL / 2}
                      y={LABEL_H + i * CELL + CELL / 2 + 3}
                      textAnchor="middle"
                      fontSize={7}
                      fill="rgba(255,255,255,0.55)"
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
                      fill="rgba(255,255,255,0.8)"
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

        {/* Color legend */}
        <div className="flex items-center gap-3 mt-4 max-w-xs mx-auto">
          <span className="text-xs text-gray-500">−1.0</span>
          <div
            className="h-3 flex-1 rounded"
            style={{
              background: "linear-gradient(to right, rgb(239,68,68), rgb(31,41,55), rgb(59,130,246))",
            }}
          />
          <span className="text-xs text-gray-500">+1.0</span>
        </div>
      </div>

      {/* Fixed tooltip */}
      {tooltip && (
        <div
          className="fixed pointer-events-none z-50 bg-gray-900 border border-gray-700 rounded px-3 py-2 text-xs shadow-xl"
          style={{ left: tooltip.x + 14, top: tooltip.y - 10 }}
        >
          <p className="text-gray-300 font-medium">
            {FEATURE_LABELS[features[tooltip.j]] ?? features[tooltip.j]}
          </p>
          <p className="text-gray-300 font-medium">
            × {FEATURE_LABELS[features[tooltip.i]] ?? features[tooltip.i]}
          </p>
          <p
            className="font-mono font-bold mt-1"
            style={{
              color:
                matrix[tooltip.i][tooltip.j] == null
                  ? "#6b7280"
                  : matrix[tooltip.i][tooltip.j]! > 0
                  ? "#60a5fa"
                  : "#f87171",
            }}
          >
            {matrix[tooltip.i][tooltip.j]?.toFixed(3) ?? "–"}
          </p>
        </div>
      )}
    </div>
  );
}
