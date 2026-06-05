import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { UmapPoint2D } from "../types/umap";

interface Props {
  points: UmapPoint2D[];
  selectedSongId: string | null;
  getColor: (songId: string) => string;
  onSelect: (songId: string | null) => void;
  xLabel?: string;
  yLabel?: string;
}

interface Transform {
  scale: number;
  offsetX: number;
  offsetY: number;
}

interface Tooltip {
  x: number;
  y: number;
  text: string;
}

const HIT_RADIUS = 14; // px — how close you need to click/hover to a point
const PAN_MARGIN = 0.35; // fraction of canvas that must still show data
const DATA_PAD = 0.15; // fractional padding added around the data cloud
const MAX_ZOOM_FACTOR = 40; // how much you can zoom in relative to fit-all view
const POINT_RADIUS = 7;
const SELECTED_RADIUS = 11;
const DPR = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;

export function UmapCanvas2D({ points, selectedSongId, getColor, onSelect, xLabel, yLabel }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const transformRef = useRef<Transform>({ scale: 1, offsetX: 0, offsetY: 0 });
  const dragRef = useRef({ active: false, lastX: 0, lastY: 0, moved: false });
  const rafRef = useRef<number>(0);
  const selectedIdRef = useRef(selectedSongId);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);

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
    const dx = (maxX - minX) * DATA_PAD;
    const dy = (maxY - minY) * DATA_PAD;
    return { minX: minX - dx, maxX: maxX + dx, minY: minY - dy, maxY: maxY + dy };
  }, [points]);

  // ── helpers ───────────────────────────────────────────────────────────────

  const canvasSize = useCallback((): [number, number] => {
    const c = canvasRef.current;
    return c ? [c.width / DPR, c.height / DPR] : [0, 0];
  }, []);

  const fitScale = useCallback((): number => {
    const [W, H] = canvasSize();
    if (W === 0) return 1;
    const dataW = dataBounds.maxX - dataBounds.minX;
    const dataH = dataBounds.maxY - dataBounds.minY;
    return Math.min(W / dataW, H / dataH) * 0.85;
  }, [dataBounds, canvasSize]);

  const clampTransform = useCallback((t: Transform): Transform => {
    const [W, H] = canvasSize();
    const minScale = fitScale();
    const maxScale = minScale * MAX_ZOOM_FACTOR;
    const s = Math.max(minScale, Math.min(maxScale, t.scale));

    const minOX = W * PAN_MARGIN - dataBounds.maxX * s;
    const maxOX = W * (1 - PAN_MARGIN) - dataBounds.minX * s;
    const minOY = H * PAN_MARGIN - dataBounds.maxY * s;
    const maxOY = H * (1 - PAN_MARGIN) - dataBounds.minY * s;

    return {
      scale: s,
      offsetX: Math.max(minOX, Math.min(maxOX, t.offsetX)),
      offsetY: Math.max(minOY, Math.min(maxOY, t.offsetY)),
    };
  }, [dataBounds, fitScale, canvasSize]);

  const initTransform = useCallback(() => {
    const [W, H] = canvasSize();
    if (W === 0 || points.length === 0) return;
    const s = fitScale();
    const dataW = dataBounds.maxX - dataBounds.minX;
    const dataH = dataBounds.maxY - dataBounds.minY;
    transformRef.current = clampTransform({
      scale: s,
      offsetX: (W - dataW * s) / 2 - dataBounds.minX * s,
      offsetY: (H - dataH * s) / 2 - dataBounds.minY * s,
    });
  }, [points.length, dataBounds, fitScale, clampTransform, canvasSize]);

  const toScreen = (dx: number, dy: number): [number, number] => {
    const { scale, offsetX, offsetY } = transformRef.current;
    return [dx * scale + offsetX, dy * scale + offsetY];
  };

  const hitTest = (sx: number, sy: number): UmapPoint2D | null => {
    let best: UmapPoint2D | null = null;
    let bestD = HIT_RADIUS * HIT_RADIUS;
    for (const p of points) {
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

    // Regular points
    for (const p of points) {
      if (p.song_id === selId) continue;
      const [sx, sy] = toScreen(p.x, p.y);
      ctx.beginPath();
      ctx.arc(sx * DPR, sy * DPR, POINT_RADIUS * DPR, 0, Math.PI * 2);
      ctx.fillStyle = getColor(p.song_id);
      ctx.globalAlpha = 0.82;
      ctx.fill();
    }

    // Selected point on top
    const sel = selId ? points.find((p) => p.song_id === selId) : null;
    if (sel) {
      const [sx, sy] = toScreen(sel.x, sel.y);
      ctx.beginPath();
      ctx.arc(sx * DPR, sy * DPR, (SELECTED_RADIUS + 5) * DPR, 0, Math.PI * 2);
      ctx.fillStyle = "#f59e0b33";
      ctx.globalAlpha = 1;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(sx * DPR, sy * DPR, SELECTED_RADIUS * DPR, 0, Math.PI * 2);
      ctx.fillStyle = "#f59e0b";
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }, [points, getColor]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep drawRef in sync so scheduleRedraw doesn't need draw as a dep —
  // if scheduleRedraw were to depend on draw, it would recreate whenever
  // getColor changes (App polls songs), which would trigger the
  // [points, initTransform, scheduleRedraw] effect and reset the camera.
  const drawRef = useRef(draw);
  useEffect(() => { drawRef.current = draw; }, [draw]);

  const scheduleRedraw = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => drawRef.current());
  }, []); // stable — never changes reference

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
    // Clamp the scale first, then derive the actual zoom factor from it
    // so the camera doesn't drift when already at the zoom limit.
    const desiredScale = t.scale * (e.deltaY < 0 ? 1.12 : 1 / 1.12);
    const minScale = fitScale();
    const maxScale = minScale * MAX_ZOOM_FACTOR;
    const clampedScale = Math.max(minScale, Math.min(maxScale, desiredScale));
    const actualFactor = clampedScale / t.scale;
    const newTransform = clampTransform({
      scale: clampedScale,
      offsetX: mx * (1 - actualFactor) + t.offsetX * actualFactor,
      offsetY: my * (1 - actualFactor) + t.offsetY * actualFactor,
    });
    transformRef.current = newTransform;
    scheduleRedraw();
    setTooltip(null);
  }, [clampTransform, fitScale, scheduleRedraw]);

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
      const dx = x - drag.lastX;
      const dy = y - drag.lastY;
      if (Math.abs(dx) + Math.abs(dy) > 2) drag.moved = true;
      drag.lastX = x;
      drag.lastY = y;
      const t = transformRef.current;
      transformRef.current = clampTransform({
        scale: t.scale,
        offsetX: t.offsetX + dx,
        offsetY: t.offsetY + dy,
      });
      scheduleRedraw();
      return;
    }

    // Hover hit-test
    const hit = hitTest(x, y);
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
    setTooltip(null);
  };

  return (
    <div ref={containerRef} className="relative w-full h-full overflow-hidden bg-gray-950">
      <canvas
        ref={canvasRef}
        className="absolute inset-0 cursor-default"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onContextMenu={(e) => e.preventDefault()}
      />

      {/* Axis labels */}
      {xLabel && (
        <div className="pointer-events-none absolute bottom-2 left-0 right-0 flex justify-center">
          <span className="text-[11px] text-gray-500 tracking-wide">{xLabel}</span>
        </div>
      )}
      {yLabel && (
        <div className="pointer-events-none absolute left-1 top-0 bottom-0 flex items-center">
          <span
            className="text-[11px] text-gray-500 tracking-wide"
            style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
          >
            {yLabel}
          </span>
        </div>
      )}

      {tooltip && (
        <div
          className="pointer-events-none absolute z-10 px-2 py-1 rounded text-xs text-gray-100 bg-gray-800 border border-gray-700 shadow-lg whitespace-nowrap"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
}
