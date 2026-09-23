import { useState } from 'react';
import type { Song } from '../types/song';
import { PlayButton } from './PlayButton';
import { SongDetails } from './SongDetails';

export function SongCard({ song }: { song: Song }) {
  const [expanded, setExpanded] = useState(false);
  const dsp = song.dsp_features;
  const file = song.file_metadata;

  return (
    <div className="border border-gray-800 rounded-lg overflow-hidden bg-gray-900/30">
      <div className="flex items-center gap-3 px-3 py-3 hover:bg-gray-800/50 transition-colors">
        <PlayButton songId={song.id} />
        <button
          className="flex-1 flex items-center gap-3 min-w-0 text-left"
          onClick={() => setExpanded(e => !e)}
        >
          <div className="flex-1 min-w-0">
            <div className="font-medium text-white truncate">{song.title ?? 'Unknown'}</div>
            <div className="text-sm text-gray-400 truncate">{song.artist ?? 'Unknown'}</div>
          </div>
          <div className="hidden sm:flex items-center gap-1.5 shrink-0 flex-wrap justify-end max-w-xs">
            {dsp?.key && dsp.scale && (
              <span className="text-xs bg-gray-800 text-gray-300 px-2 py-0.5 rounded font-mono">
                {dsp.key} {dsp.scale}
              </span>
            )}
            {dsp?.bpm != null && (
              <span className="text-xs bg-gray-800 text-gray-300 px-2 py-0.5 rounded font-mono">
                {Math.round(dsp.bpm)} BPM
              </span>
            )}
            {file?.duration_seconds != null && (
              <span className="text-xs bg-gray-800 text-gray-300 px-2 py-0.5 rounded font-mono">
                {Math.floor(file.duration_seconds / 60)}:{Math.floor(file.duration_seconds % 60).toString().padStart(2, '0')}
              </span>
            )}
          </div>
          <svg
            className={`w-4 h-4 text-gray-500 shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {expanded && (
        <div className="border-t border-gray-800 px-4 py-4">
          <SongDetails song={song} />
        </div>
      )}
    </div>
  );
}
