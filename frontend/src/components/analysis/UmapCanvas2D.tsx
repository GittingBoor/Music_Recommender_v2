import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { UmapPoint2D } from "../../types/umap";
import { COLOR, FONT_MONO } from "../../theme";

/** Feature names of a scatter plot; without them the map is a unitless UMAP. */
export interface PlotAxes {
  x: string;
  y: string;
}

interface Props {
  points: UmapPoint2D[];
  selectedSongId: string | null;
  getColor: (songId: string) => string;
  /** Hidden points are neither drawn nor hoverable; the selected one always shows. */
  isVisible: (songId: string) => boolean;
  onSelect: (songId: string | null) => void;
  /** Dot radius in CSS px. */
  pointRadius: number;
  /** Set for a scatter plot: axes stretch independently and get value ticks. */
  axes?: PlotAxes | null;
}

/** Data → screen: sx = x·kx + ox, sy = oy − y·ky (y grows upwards). */
interface Transform {
  kx: number;
  ky: number;
  ox: number;
  oy: number;
}

interface Tooltip {
  x: number;
  y: number;
  text: string;
}

const MIN_HIT_RADIUS = 14; // px — how close you need to click/hover to a point
const PAN_MARGIN = 0.35; // fraction of canvas that must still show data
const DATA_PAD = 0.15; // fractional padding added around the data cloud
const FIT_FILL = 0.85; // share of the canvas the padded data fills at zoom 1
const MAX_ZOOM_FACTOR = 40; // how much you can zoom in relative to fit-all view
const SELECTED_GROW = 1; // selected core is this much larger than a dot
const SELECTED_RING_GAP = 6; // signal ring sits this far outside a dot
// Neighbour links: hinted on hover, committed on selection.
// Paper-white reads as "connection" against every genre colour on the dark ground.
const LINK_COLOR = COLOR.ink;
const LINK_ALPHA_HOVER = 0.22;
const LINK_ALPHA_SELECTED = 0.8;
const LINK_WIDTH_HOVER = 1;
const LINK_WIDTH_SELECTED = 2;
// Axis ticks: target spacing between labels, and the corner zones where
// x- and y-labels (and the axis titles) would collide.
const TICK_SPACING_X = 90;
const TICK_SPACING_Y = 56;
const TICK_FONT_PX = 10;
const TICK_INSET = 6;
const Y_LABEL_ZONE = 44; // px from the left kept free of x-labels
const X_LABEL_ZONE = 22; // px from the bottom kept free of y-labels
const TITLE_ZONE = 30; // px from the top kept free of y-labels (y-axis title)
const DPR = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;

/** Round steps (1, 2, 5 × 10ⁿ) covering [min, max] with about `count` ticks. */
function niceTicks(min: number, max: number, count: number): { values: number[]; decimals: number } {
  const range = max - min;
  if (!(range > 0) || count < 1) return { values: [], decimals: 0 };
  const raw = range / count;
  const exp = Math.floor(Math.log10(raw));
  const mag = 10 ** exp;
  const n = raw / mag;
  const step = (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * mag;
  const values: number[] = [];
  // Multiply instead of accumulating so float error doesn't drift.
  for (let i = Math.ceil(min / step); i * step <= max; i++) values.push(i * step);
  return { values, decimals: Math.max(0, -Math.floor(Math.log10(step))) };
}

export function UmapCanvas2D({
  points, selectedSongId, getColor, isVisible, onSelect, pointRadius, axes,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const transformRef = useRef<Transform>({ kx: 1, ky: 1, ox: 0, oy: 0 });
  const dragRef = useRef({ active: false, lastX: 0, lastY: 0, moved: false });
  const rafRef = useRef<number>(0);
  const selectedIdRef = useRef(selectedSongId);
  const hoveredIdRef = useRef<string | null>(null);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);

  // A UMAP has no units, so only distances matter: keep both axes on one scale.
  const equalAspect = !axes;

  const pointById = useMemo(
    () => new Map(points.map((p) => [p.song_id, p])),
    [points]
  );

  // ── data bounds (with padding) ────────────────────────────────────────────
  const dataBounds = useMemo(() => {
    if (points.length === 0) return { minX: -1, maxX: 1, minY: -1, maxY: 1 };
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const p of points) {
      if (p.x < minX) minX = p.x;
      if (p.x > maxX) maxX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.y > maxY) maxY = p.y;
    }
    // A feature with a single value across the library would have zero extent.
    const dx = maxX > minX ? (maxX - minX) * DATA_PAD : Math.abs(maxX) * 0.1 || 1;
    const dy = maxY > minY ? (maxY - minY) * DATA_PAD : Math.abs(maxY) * 0.1 || 1;
    return { minX: minX - dx, maxX: maxX + dx, minY: minY - dy, maxY: maxY + dy };
  }, [points]);

  // ── helpers ───────────────────────────────────────────────────────────────

  const canvasSize = useCallback((): [number, number] => {
    const c = canvasRef.current;
    return c ? [c.width / DPR, c.height / DPR] : [0, 0];
  }, []);

  /** Scales at zoom 1, where the whole data cloud fits. */
  const baseScale = useCallback((): [number, number] => {
    const [W, H] = canvasSize();
    if (W === 0) return [1, 1];
    const bx = (W / (dataBounds.maxX - dataBounds.minX)) * FIT_FILL;
    const by = (H / (dataBounds.maxY - dataBounds.minY)) * FIT_FILL;
    if (equalAspect) {
      const s = Math.min(bx, by);
      return [s, s];
    }
    return [bx, by];
  }, [dataBounds, canvasSize, equalAspect]);

  const clampTransform = useCallback((t: Transform): Transform => {
    const [W, H] = canvasSize();
    const [bx, by] = baseScale();
    const zoom = Math.max(1, Math.min(MAX_ZOOM_FACTOR, t.kx / bx));
    const kx = bx * zoom;
    const ky = by * zoom;

    const minOX = W * PAN_MARGIN - dataBounds.maxX * kx;
    const maxOX = W * (1 - PAN_MARGIN) - dataBounds.minX * kx;
    const minOY = H * PAN_MARGIN + dataBounds.minY * ky;
    const maxOY = H * (1 - PAN_MARGIN) + dataBounds.maxY * ky;

    return {
      kx,
      ky,
      ox: Math.max(minOX, Math.min(maxOX, t.ox)),
      oy: Math.max(minOY, Math.min(maxOY, t.oy)),
    };
  }, [dataBounds, baseScale, canvasSize]);

  const initTransform = useCallback(() => {
    const [W, H] = canvasSize();
    if (W === 0 || points.length === 0) return;
    const [kx, ky] = baseScale();
    const dataW = dataBounds.maxX - dataBounds.minX;
    const dataH = dataBounds.maxY - dataBounds.minY;
    transformRef.current = clampTransform({
      kx,
      ky,
      ox: (W - dataW * kx) / 2 - dataBounds.minX * kx,
      oy: (H + dataH * ky) / 2 + dataBounds.minY * ky,
    });
  }, [points.length, dataBounds, baseScale, clampTransform, canvasSize]);

  const toScreen = (dx: number, dy: number): [number, number] => {
    const { kx, ky, ox, oy } = transformRef.current;
    return [dx * kx + ox, oy - dy * ky];
  };

  const hitTest = (sx: number, sy: number): UmapPoint2D | null => {
    const hitRadius = Math.max(MIN_HIT_RADIUS, pointRadius + 4);
    let best: UmapPoint2D | null = null;
    let bestD = hitRadius * hitRadius;
    for (const p of points) {
      if (p.song_id !== selectedIdRef.current && !isVisible(p.song_id)) continue;
      const [px, py] = toScreen(p.x, p.y);
      const d = (px - sx) ** 2 + (py - sy) ** 2;
      if (d < bestD) { bestD = d; best = p; }
    }
    return best;
  };

  // ── draw ──────────────────────────────────────────────────────────────────

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || points.length === 0) return;

    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const selId = selectedIdRef.current;
    const shown = (id: string) => id === selId || isVisible(id);

    // Value ticks of a scatter plot, for the part of the data currently in view
    const { kx, ky, ox, oy } = transformRef.current;
    const cssW = W / DPR;
    const cssH = H / DPR;
    const xTicks = axes ? niceTicks(-ox / kx, (cssW - ox) / kx, cssW / TICK_SPACING_X) : null;
    const yTicks = axes ? niceTicks((oy - cssH) / ky, oy / ky, cssH / TICK_SPACING_Y) : null;

    // Grid first, so everything else sits on top of it
    if (xTicks && yTicks) {
      ctx.lineWidth = 1;
      ctx.strokeStyle = COLOR.line;
      ctx.beginPath();
      for (const v of xTicks.values) {
        const sx = Math.round((v * kx + ox) * DPR) + 0.5;
        ctx.moveTo(sx, 0);
        ctx.lineTo(sx, H);
      }
      for (const v of yTicks.values) {
        const sy = Math.round((oy - v * ky) * DPR) + 0.5;
        ctx.moveTo(0, sy);
        ctx.lineTo(W, sy);
      }
      ctx.stroke();
    }

    // Neighbour links — drawn before the points so those sit on top of them
    const drawLinks = (fromId: string, alpha: number, width: number) => {
      const from = pointById.get(fromId);
      if (!from) return;
      const [fx, fy] = toScreen(from.x, from.y);
      ctx.globalAlpha = alpha;
      ctx.lineWidth = width * DPR;
      ctx.strokeStyle = LINK_COLOR;
      for (const neighborId of from.neighbors) {
        const to = pointById.get(neighborId);
        if (!to || !shown(neighborId)) continue;
        const [tx, ty] = toScreen(to.x, to.y);
        ctx.beginPath();
        ctx.moveTo(fx * DPR, fy * DPR);
        ctx.lineTo(tx * DPR, ty * DPR);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    };

    const hoverId = hoveredIdRef.current;
    if (hoverId && hoverId !== selId) {
      drawLinks(hoverId, LINK_ALPHA_HOVER, LINK_WIDTH_HOVER);
    }
    if (selId) {
      drawLinks(selId, LINK_ALPHA_SELECTED, LINK_WIDTH_SELECTED);
    }

    // Regular points — a thin ground-coloured ring keeps overlapping dots apart
    ctx.lineWidth = 1 * DPR;
    ctx.strokeStyle = COLOR.ground;
    for (const p of points) {
      if (p.song_id === selId || !isVisible(p.song_id)) continue;
      const [sx, sy] = toScreen(p.x, p.y);
      ctx.beginPath();
      ctx.arc(sx * DPR, sy * DPR, pointRadius * DPR, 0, Math.PI * 2);
      ctx.fillStyle = getColor(p.song_id);
      ctx.globalAlpha = 0.9;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.stroke();
    }

    // Selected point on top: paper-white core inside a signal ring — reads
    // apart from every genre hue, including the orange one.
    const sel = selId ? pointById.get(selId) : null;
    if (sel) {
      const [sx, sy] = toScreen(sel.x, sel.y);
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(sx * DPR, sy * DPR, (pointRadius + SELECTED_RING_GAP) * DPR, 0, Math.PI * 2);
      ctx.lineWidth = 2 * DPR;
      ctx.strokeStyle = COLOR.signal;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(sx * DPR, sy * DPR, (pointRadius + SELECTED_GROW) * DPR, 0, Math.PI * 2);
      ctx.fillStyle = COLOR.ink;
      ctx.fill();
      ctx.lineWidth = 2 * DPR;
      ctx.strokeStyle = COLOR.ground;
      ctx.stroke();
    }

    // Tick labels last, pinned to the left and bottom edge on a ground backing
    if (xTicks && yTicks) {
      ctx.font = `${TICK_FONT_PX * DPR}px ${FONT_MONO}`;
      const label = (text: string, x: number, y: number, align: CanvasTextAlign) => {
        const w = ctx.measureText(text).width;
        const left = align === "center" ? x - w / 2 : x;
        ctx.fillStyle = COLOR.ground;
        ctx.globalAlpha = 0.85;
        ctx.fillRect(left - 2 * DPR, y - (TICK_FONT_PX / 2 + 2) * DPR, w + 4 * DPR, (TICK_FONT_PX + 4) * DPR);
        ctx.globalAlpha = 1;
        ctx.fillStyle = COLOR.ink3;
        ctx.textAlign = align;
        ctx.textBaseline = "middle";
        ctx.fillText(text, x, y);
      };
      for (const v of xTicks.values) {
        const sx = v * kx + ox;
        if (sx < Y_LABEL_ZONE || sx > cssW - 16) continue;
        label(v.toFixed(xTicks.decimals), sx * DPR, (cssH - TICK_INSET - TICK_FONT_PX / 2) * DPR, "center");
      }
      for (const v of yTicks.values) {
        const sy = oy - v * ky;
        if (sy < TITLE_ZONE || sy > cssH - X_LABEL_ZONE) continue;
        label(v.toFixed(yTicks.decimals), TICK_INSET * DPR, sy * DPR, "left");
      }
    }
    ctx.globalAlpha = 1;
  }, [points, getColor, isVisible, pointRadius, axes, pointById]); // eslint-disable-line react-hooks/exhaustive-deps

  // drawRef lets scheduleRedraw stay stable — if it depended on draw, it would
  // recreate whenever getColor changes (App polls songs), which would trigger
  // the [points, initTransform, scheduleRedraw] effect and reset the camera.
  const drawRef = useRef(draw);

  const scheduleRedraw = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => drawRef.current());
  }, []); // stable — never changes reference

  // Colours, visibility or dot size changed: repaint without touching the camera
  useEffect(() => {
    drawRef.current = draw;
    scheduleRedraw();
  }, [draw, scheduleRedraw]);

  // ── resize observer ───────────────────────────────────────────────────────

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const ro = new ResizeObserver(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const { width, height } = container.getBoundingClientRect();
      canvas.width = width * DPR;
      canvas.height = height * DPR;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      initTransform();
      scheduleRedraw();
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, [initTransform, scheduleRedraw]);

  // Re-init + redraw when points change
  useEffect(() => {
    initTransform();
    scheduleRedraw();
  }, [points, initTransform, scheduleRedraw]);

  // Sync ref and redraw when selection changes (no transform reset, no draw recreation)
  useEffect(() => {
    selectedIdRef.current = selectedSongId;
    scheduleRedraw();
  }, [selectedSongId, scheduleRedraw]);

  // ── mouse events ──────────────────────────────────────────────────────────

  const getCanvasXY = (e: React.MouseEvent): [number, number] => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  };

  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const t = transformRef.current;
    // Clamp the zoom first, then derive the actual factor from it
    // so the camera doesn't drift when already at the zoom limit.
    const [bx] = baseScale();
    const zoom = t.kx / bx;
    const desiredZoom = zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12);
    const clampedZoom = Math.max(1, Math.min(MAX_ZOOM_FACTOR, desiredZoom));
    const f = clampedZoom / zoom;
    transformRef.current = clampTransform({
      kx: t.kx * f,
      ky: t.ky * f,
      ox: mx * (1 - f) + t.ox * f,
      oy: my * (1 - f) + t.oy * f,
    });
    scheduleRedraw();
    setTooltip(null);
  }, [clampTransform, baseScale, scheduleRedraw]);

  // Attach wheel with non-passive listener (need preventDefault)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.addEventListener("wheel", handleWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", handleWheel);
  }, [handleWheel]);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    const [x, y] = getCanvasXY(e);
    dragRef.current = { active: true, lastX: x, lastY: y, moved: false };
    setTooltip(null);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const [x, y] = getCanvasXY(e);
    const drag = dragRef.current;

    if (drag.active) {
      if (hoveredIdRef.current !== null) hoveredIdRef.current = null;
      const dx = x - drag.lastX;
      const dy = y - drag.lastY;
      if (Math.abs(dx) + Math.abs(dy) > 2) drag.moved = true;
      drag.lastX = x;
      drag.lastY = y;
      const t = transformRef.current;
      transformRef.current = clampTransform({ ...t, ox: t.ox + dx, oy: t.oy + dy });
      scheduleRedraw();
      return;
    }

    // Hover hit-test
    const hit = hitTest(x, y);
    if (hoveredIdRef.current !== (hit?.song_id ?? null)) {
      hoveredIdRef.current = hit?.song_id ?? null;
      scheduleRedraw();
    }
    if (hit) {
      const [sx, sy] = toScreen(hit.x, hit.y);
      const canvas = canvasRef.current!;
      const rect = canvas.getBoundingClientRect();
      // Offset tooltip so it doesn't cover the point
      const tipX = sx + 14 > rect.width - 120 ? sx - 130 : sx + 14;
      const tipY = sy - 10 < 0 ? sy + 14 : sy - 10;
      setTooltip({ x: tipX, y: tipY, text: hit.title ?? hit.song_id });
    } else {
      setTooltip(null);
    }
  };

  const handleMouseUp = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    const drag = dragRef.current;
    drag.active = false;
    if (!drag.moved) {
      const [x, y] = getCanvasXY(e);
      const hit = hitTest(x, y);
      if (hit) onSelect(hit.song_id); // clicking empty space keeps the last selection
    }
    drag.moved = false;
  };

  const handleMouseLeave = () => {
    dragRef.current.active = false;
    dragRef.current.moved = false;
    if (hoveredIdRef.current !== null) {
      hoveredIdRef.current = null;
      scheduleRedraw();
    }
    setTooltip(null);
  };

  return (
    <div ref={containerRef} className="relative w-full h-full overflow-hidden bg-ground">
      <canvas
        ref={canvasRef}
        className="absolute inset-0 cursor-default touch-none"
        onPointerDown={handleMouseDown}
        onPointerMove={handleMouseMove}
        onPointerUp={handleMouseUp}
        onPointerLeave={handleMouseLeave}
        onContextMenu={(e) => e.preventDefault()}
      />

      {/* Axis titles at the ends the values grow towards (phones: below the legend button) */}
      {axes && (
        <>
          <span className="pointer-events-none absolute right-3 bottom-7 px-1 bg-ground/85 font-mono text-2xs text-ink-2">
            {axes.x} →
          </span>
          <span className="pointer-events-none absolute left-1 top-12 md:top-2 px-1 bg-ground/85 font-mono text-2xs text-ink-2">
            ↑ {axes.y}
          </span>
        </>
      )}

      {tooltip && (
        <div
          className="pointer-events-none absolute z-10 px-2 py-1 rounded-sm text-xs text-ink bg-raised border border-line-strong whitespace-nowrap"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
}
