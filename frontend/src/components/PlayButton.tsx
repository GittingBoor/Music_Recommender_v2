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
      className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-colors ${
        isActive
          ? "bg-violet-600 hover:bg-violet-700 text-white"
          : "bg-gray-800 hover:bg-gray-700 text-gray-300"
      } ${className}`}
    >
      {isActive ? (
        // Pause icon
        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="5" width="4" height="14" rx="1" />
          <rect x="14" y="5" width="4" height="14" rx="1" />
        </svg>
      ) : (
        // Play icon (offset slightly to visually center)
        <svg className="w-3.5 h-3.5 translate-x-px" viewBox="0 0 24 24" fill="currentColor">
          <path d="M8 5v14l11-7z" />
        </svg>
      )}
    </button>
  );
}
