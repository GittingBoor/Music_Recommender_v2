import { useState } from 'react';
import type { Song } from '../types/song';
import { PlayButton } from './PlayButton';
import { SongDetails } from './SongDetails';

/** One line of the tracklist; expands into the full field dump. */
export function SongCard({ song }: { song: Song }) {
  const [expanded, setExpanded] = useState(false);
  const dsp = song.dsp_features;
  const file = song.file_metadata;

  return (
    <div className={`border-b border-line ${expanded ? 'bg-panel' : ''}`}>
      <div className="flex items-center gap-3 pl-1 pr-2 h-14 hover:bg-raised/60">
        <PlayButton songId={song.id} />
        <button
          className="flex-1 flex items-center gap-4 min-w-0 h-full text-left"
          onClick={() => setExpanded(e => !e)}
          aria-expanded={expanded}
        >
          <div className="flex-1 min-w-0">
            <div className="text-base font-medium text-ink truncate">{song.title ?? 'Unknown'}</div>
            <div className="text-sm text-ink-3 truncate">{song.artist ?? 'Unknown'}</div>
          </div>
          <div className="hidden sm:flex items-baseline shrink-0 font-mono text-xs text-ink-2 tabular-nums">
            <span className="w-24 text-right">
              {dsp?.key && dsp.scale ? `${dsp.key} ${dsp.scale}` : ''}
            </span>
            <span className="w-20 text-right">
              {dsp?.bpm != null && (
                <>{Math.round(dsp.bpm)}<span className="text-ink-4"> bpm</span></>
              )}
            </span>
            <span className="w-14 text-right">
              {file?.duration_seconds != null &&
                `${Math.floor(file.duration_seconds / 60)}:${Math.floor(file.duration_seconds % 60).toString().padStart(2, '0')}`}
            </span>
          </div>
          <svg
            className={`w-3.5 h-3.5 ml-2 shrink-0 transition-transform ${expanded ? 'rotate-180 text-ink-2' : 'text-ink-4'}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="square" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {expanded && (
        <div className="pl-11 pr-4 pt-3 pb-8">
          <SongDetails song={song} />
        </div>
      )}
    </div>
  );
}
