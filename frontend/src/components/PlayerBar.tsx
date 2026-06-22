import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { subscribe, getSnapshot, getAudio, toggle, seek, skip } from "../audio/player";
import type { Song } from "../types/song";

function fmt(s: number): string {
  if (!isFinite(s) || isNaN(s)) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

interface Props {
  songs: Song[];
}

export function PlayerBar({ songs }: Props) {
  const { currentId, playing } = useSyncExternalStore(subscribe, getSnapshot);

  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration]       = useState(0);
  const [dragging, setDragging]        = useState(false);
  const [dragValue, setDragValue]      = useState(0);

  const barRef = useRef<HTMLDivElement>(null);

  // Attach timeupdate / metadata listeners directly to the audio element.
  // Re-attaches whenever currentId changes (new audio source loaded).
  useEffect(() => {
    const audio = getAudio();
    if (!audio) return;

    const onTime = () => { if (!dragging) setCurrentTime(audio.currentTime); };
    const onMeta = () => setDuration(audio.duration || 0);
    const onEnded = () => { setCurrentTime(0); setDuration(0); };

    audio.addEventListener("timeupdate",     onTime);
    audio.addEventListener("loadedmetadata", onMeta);
    audio.addEventListener("ended",          onEnded);
    // Read initial values in case already loaded
    if (audio.duration) { setDuration(audio.duration); setCurrentTime(audio.currentTime); }

    return () => {
      audio.removeEventListener("timeupdate",     onTime);
      audio.removeEventListener("loadedmetadata", onMeta);
      audio.removeEventListener("ended",          onEnded);
    };
  }, [currentId, dragging]);

  const song = songs.find((s) => s.id === currentId) ?? null;
  const progress = duration > 0 ? currentTime / duration : 0;
  const displayTime = dragging ? dragValue : currentTime;

  // ── seekbar pointer interaction ──────────────────────────────────────────
  function calcSeekFromEvent(e: React.PointerEvent | PointerEvent): number {
    const bar = barRef.current;
    if (!bar || !duration) return 0;
    const rect = bar.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    return frac * duration;
  }

  function onSeekPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
    setDragging(true);
    setDragValue(calcSeekFromEvent(e));
  }

  function onSeekPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    setDragValue(calcSeekFromEvent(e));
  }

  function onSeekPointerUp(e: React.PointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    const t = calcSeekFromEvent(e);
    seek(t);
    setCurrentTime(t);
    setDragging(false);
  }

  if (!currentId) return null;

  const fillPct = `${(dragging ? dragValue / (duration || 1) : progress) * 100}%`;

  return (
    <div className="flex-shrink-0 border-t border-gray-800 bg-gray-950">

      {/* seekbar */}
      <div
        ref={barRef}
        className="relative h-1 bg-gray-800 cursor-pointer group"
        onPointerDown={onSeekPointerDown}
        onPointerMove={onSeekPointerMove}
        onPointerUp={onSeekPointerUp}
      >
        <div
          className="absolute inset-y-0 left-0 bg-violet-500 group-hover:bg-violet-400 transition-colors"
          style={{ width: fillPct }}
        />
        {/* larger hit-area + thumb on hover */}
        <div
          className="absolute -top-1 -bottom-1 -left-1 -right-1 group"
          aria-hidden
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full bg-white opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
          style={{ left: fillPct }}
        />
      </div>

      {/* controls row */}
      <div className="flex items-center gap-3 px-4 h-11">

        {/* skip back 15s */}
        <button
          onClick={() => skip(-15)}
          className="text-gray-400 hover:text-white transition-colors"
          aria-label="Skip back 15 seconds"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
            <text x="12" y="14" textAnchor="middle" fontSize="5.5" fill="currentColor" fontWeight="700">15</text>
          </svg>
        </button>

        {/* play / pause */}
        <button
          onClick={() => currentId && toggle(currentId)}
          className="w-8 h-8 rounded-full bg-white text-gray-900 flex items-center justify-center hover:bg-gray-200 transition-colors shrink-0"
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? (
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="5" width="4" height="14" rx="1" />
              <rect x="14" y="5" width="4" height="14" rx="1" />
            </svg>
          ) : (
            <svg className="w-3.5 h-3.5 translate-x-px" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>

        {/* skip forward 15s */}
        <button
          onClick={() => skip(15)}
          className="text-gray-400 hover:text-white transition-colors"
          aria-label="Skip forward 15 seconds"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 5V1l5 5-5 5V7c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6h2c0 4.42-3.58 8-8 8s-8-3.58-8-8 3.58-8 8-8z"/>
            <text x="12" y="14" textAnchor="middle" fontSize="5.5" fill="currentColor" fontWeight="700">15</text>
          </svg>
        </button>

        {/* title / artist */}
        <div className="flex-1 min-w-0 ml-1">
          <span className="text-sm text-white font-medium truncate block leading-tight">
            {song?.title ?? "Unknown"}
          </span>
          <span className="text-xs text-gray-500 truncate block leading-tight">
            {song?.artist ?? ""}
          </span>
        </div>

        {/* time */}
        <span className="text-xs font-mono text-gray-500 shrink-0 tabular-nums">
          {fmt(displayTime)}
          <span className="text-gray-700"> / </span>
          {fmt(duration)}
        </span>

      </div>
    </div>
  );
}
