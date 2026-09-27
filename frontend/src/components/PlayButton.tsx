import { useSyncExternalStore } from "react";
import { toggle, subscribe, getSnapshot } from "../audio/player";

interface Props {
  songId: string;
  className?: string;
}

export function PlayButton({ songId, className = "" }: Props) {
  const { currentId, playing } = useSyncExternalStore(subscribe, getSnapshot);
  const isActive = currentId === songId && playing;

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        toggle(songId);
      }}
      aria-label={isActive ? "Pause" : "Play"}
      className={`shrink-0 w-7 h-7 rounded-sm flex items-center justify-center ${
        isActive
          ? "bg-signal text-ground"
          : "text-ink-3 hover:text-ink hover:bg-line"
      } ${className}`}
    >
      {isActive ? (
        // Pause icon
        <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
          <rect x="5" y="4" width="5" height="16" />
          <rect x="14" y="4" width="5" height="16" />
        </svg>
      ) : (
        // Play icon (offset slightly to visually center)
        <svg className="w-3 h-3 translate-x-px" viewBox="0 0 24 24" fill="currentColor">
          <path d="M6 4v16l14-8z" />
        </svg>
      )}
    </button>
  );
}
