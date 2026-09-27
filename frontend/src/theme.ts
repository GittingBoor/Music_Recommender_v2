// Hex mirror of the colour tokens in index.css, for places that can't read
// CSS variables: Recharts props, canvas drawing, inline SVG fills.
import type { CSSProperties } from "react";

export const COLOR = {
  ground: "#11100e",
  panel: "#161513",
  raised: "#1e1c19",
  line: "#2a2723",
  lineStrong: "#3d3933",
  ink: "#ede9e1",
  ink2: "#b0aa9f",
  ink3: "#8a857b",
  ink4: "#66625a",
  signal: "#ff6a2b",
  /** Single-series marks (histograms, ranked bars): colour carries no meaning there. */
  data: "#a59f93",
} as const;

export const FONT_MONO = '"IBM Plex Mono", ui-monospace, Consolas, monospace';

/** Categorical hues for identity (genres, instrument families, series).
 *  Order matters — adjacent slots are validated for colour-vision deficiency
 *  against the ground colour. Assign in order; don't reorder. */
export const SERIES = [
  "#3987e5", // blue
  "#d95926", // orange
  "#199e70", // aqua
  "#c98500", // yellow
  "#d55181", // magenta
  "#008300", // green
  "#9085e9", // violet
  "#e66767", // red
] as const;

/** Extended steps for maps with more than eight categories (UMAP genres).
 *  Past slot 8 hues repeat lighter — the legend carries identity there. */
export const SERIES_EXTENDED = [
  ...SERIES,
  "#86b6ef",
  "#ec835a",
  "#5fc79f",
  "#e3b25a",
  "#e98fb1",
  "#b7aef2",
] as const;

// ── Recharts presets ──────────────────────────────────────────────────────

/** Numeric axis: mono ticks, hairline axis, no tick marks. */
export const numericAxis = {
  tick: { fill: COLOR.ink3, fontSize: 10, fontFamily: FONT_MONO },
  axisLine: { stroke: COLOR.lineStrong },
  tickLine: false,
} as const;

/** Category axis (names): interface font, secondary ink. */
export const categoryAxis = {
  tick: { fill: COLOR.ink2, fontSize: 11 },
  axisLine: { stroke: COLOR.lineStrong },
  tickLine: false,
} as const;

export const gridProps = { stroke: COLOR.line } as const;

export const tooltipStyle: CSSProperties = {
  backgroundColor: COLOR.raised,
  border: `1px solid ${COLOR.lineStrong}`,
  borderRadius: 2,
  color: COLOR.ink,
  fontSize: 12,
  fontFamily: FONT_MONO,
  padding: "6px 10px",
  boxShadow: "none",
};

/** Spread onto <Tooltip />. */
export const tooltipProps = {
  contentStyle: tooltipStyle,
  labelStyle: { color: COLOR.ink, marginBottom: 2 },
  itemStyle: { color: COLOR.ink2, padding: 0 },
  cursor: { fill: "rgba(237, 233, 225, 0.04)" },
} as const;
