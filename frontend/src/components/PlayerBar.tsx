import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  subscribe,
  getSnapshot,
  getAudio,
  toggle,
  seek,
  skip,
  next,
  previous,
  shuffle,
  stop,
  setVolume,
} from "../audio/player";
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
  const { currentId, playing, volume } = useSyncExternalStore(subscribe, getSnapshot);

  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration]       = useState(0);
  const [dragging, setDragging]        = useState(false);
  const [dragValue, setDragValue]      = useState(0);
  const [nnHint, setNnHint]            = useState(false);

  const barRef = useRef<HTMLDivElement>(null);
  const lastVolumeRef = useRef(volume || 1);

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

  // ── volume ───────────────────────────────────────────────────────────────
  function onVolumeChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = parseFloat(e.target.value);
    if (v > 0) lastVolumeRef.current = v;
    setVolume(v);
  }

  function toggleMute() {
    if (volume > 0) {
      lastVolumeRef.current = volume;
      setVolume(0);
    } else {
      setVolume(lastVolumeRef.current || 1);
    }
  }

  function onNearestNeighbour() {
    // Placeholder: the recommendation backend does not exist yet.
    setNnHint(true);
    window.setTimeout(() => setNnHint(false), 2500);
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
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full bg-white opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
          style={{ left: fillPct }}
        />
      </div>

      {/* controls row: [ track info | transport | volume / close ] */}
      <div className="flex items-center gap-4 px-4 h-16">

        {/* ── left: track info ── */}
        <div className="flex-1 min-w-0">
          <span className="text-sm text-white font-medium truncate block leading-tight">
            {song?.title ?? "Unknown"}
          </span>
          <span className="text-xs text-gray-500 truncate block leading-tight">
            {song?.artist ?? ""}
          </span>
        </div>

        {/* ── center: transport controls ── */}
        <div className="flex items-center gap-3 shrink-0">

          {/* shuffle: random song from the database */}
          <button
            onClick={shuffle}
            className="text-gray-400 hover:text-white transition-colors"
            aria-label="Play a random song"
            title="Shuffle — play a random song"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.66 6.83l-1.41 1.41 3.13 3.13L14.5 16H20v-5.5l-2.04 2.04-2.81-2.81z" />
            </svg>
          </button>

          {/* previous song */}
          <button
            onClick={previous}
            className="text-gray-300 hover:text-white transition-colors"
            aria-label="Previous song"
            title="Previous song"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z" />
            </svg>
          </button>

          {/* skip back 15s */}
          <button
            onClick={() => skip(-15)}
            className="text-gray-400 hover:text-white transition-colors"
            aria-label="Skip back 15 seconds"
            title="Back 15 seconds"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z" />
              <text x="12" y="14" textAnchor="middle" fontSize="5.5" fill="currentColor" fontWeight="700">15</text>
            </svg>
          </button>

          {/* play / pause */}
          <button
            onClick={() => currentId && toggle(currentId)}
            className="w-9 h-9 rounded-full bg-white text-gray-900 flex items-center justify-center hover:bg-gray-200 transition-colors shrink-0"
            aria-label={playing ? "Pause" : "Play"}
          >
            {playing ? (
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="5" width="4" height="14" rx="1" />
                <rect x="14" y="5" width="4" height="14" rx="1" />
              </svg>
            ) : (
              <svg className="w-4 h-4 translate-x-px" viewBox="0 0 24 24" fill="currentColor">
                <path d="M8 5v14l11-7z" />
              </svg>
            )}
          </button>

          {/* skip forward 15s */}
          <button
            onClick={() => skip(15)}
            className="text-gray-400 hover:text-white transition-colors"
            aria-label="Skip forward 15 seconds"
            title="Forward 15 seconds"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 5V1l5 5-5 5V7c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6h2c0 4.42-3.58 8-8 8s-8-3.58-8-8 3.58-8 8-8z" />
              <text x="12" y="14" textAnchor="middle" fontSize="5.5" fill="currentColor" fontWeight="700">15</text>
            </svg>
          </button>

          {/* next song */}
          <button
            onClick={next}
            className="text-gray-300 hover:text-white transition-colors"
            aria-label="Next song"
            title="Next song"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
            </svg>
          </button>

          {/* nearest neighbour (placeholder — recommendation not implemented yet) */}
          <div className="relative">
            <button
              onClick={onNearestNeighbour}
              className="text-violet-400 hover:text-violet-300 transition-colors"
              aria-label="Play the nearest-neighbour song (coming soon)"
              title="Play the most similar song (nearest neighbour) — coming soon"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                <circle cx="18" cy="5" r="3" />
                <circle cx="6" cy="12" r="3" />
                <circle cx="18" cy="19" r="3" />
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
              </svg>
            </button>
            {nnHint && (
              <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-800 px-2 py-1 text-xs text-gray-200 shadow-lg border border-gray-700">
                Nearest-neighbour recommendation coming soon
              </div>
            )}
          </div>
        </div>

        {/* ── right: time, volume, close ── */}
        <div className="flex-1 flex items-center justify-end gap-3 min-w-0">

          {/* time */}
          <span className="text-xs font-mono text-gray-500 shrink-0 tabular-nums hidden sm:inline">
            {fmt(displayTime)}
            <span className="text-gray-700"> / </span>
            {fmt(duration)}
          </span>

          {/* volume */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={toggleMute}
              className="text-gray-400 hover:text-white transition-colors"
              aria-label={volume === 0 ? "Unmute" : "Mute"}
              title={volume === 0 ? "Unmute" : "Mute"}
            >
              {volume === 0 ? (
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
                </svg>
              )}
            </button>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={volume}
              onChange={onVolumeChange}
              className="w-20 sm:w-24 accent-violet-500 cursor-pointer"
              aria-label="Volume"
            />
          </div>

          {/* close: stop playback and hide the bar */}
          <button
            onClick={stop}
            className="text-gray-400 hover:text-white transition-colors shrink-0"
            aria-label="Close player"
            title="Close player"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
