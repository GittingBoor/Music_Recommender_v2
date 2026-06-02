import { useState } from 'react';
import type { Song } from '../types/song';

function fmtVal(val: unknown): React.ReactNode {
  if (val == null) return <span className="text-gray-700">null</span>;
  if (typeof val === 'number') {
    if (Number.isInteger(val)) return val.toString();
    return parseFloat(val.toFixed(6)).toString();
  }
  if (typeof val === 'string') return val;
  if (Array.isArray(val)) {
    if (val.length === 0) return '[]';
    if (typeof val[0] === 'number') {
      return '[' + (val as number[]).map(v => parseFloat(v.toFixed(4))).join(', ') + ']';
    }
    return (val as string[]).join(', ');
  }
  return JSON.stringify(val);
}

type Row = [string, unknown];

function KVTable({ name, rows }: { name: string; rows: Row[] }) {
  return (
    <div>
      <div className="text-xs font-mono font-semibold text-indigo-400 mb-1 mt-5 first:mt-0">{name}</div>
      <table className="w-full text-xs font-mono border border-gray-800">
        <tbody>
          {rows.map(([col, val]) => (
            <tr key={col} className="border-t border-gray-800 first:border-t-0">
              <td className="text-gray-500 px-2 py-0.5 w-52 shrink-0 align-top select-all">{col}</td>
              <td className="text-gray-200 px-2 py-0.5 break-all">{fmtVal(val)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MultiTable({ name, columns, rows }: { name: string; columns: string[]; rows: unknown[][] }) {
  return (
    <div>
      <div className="text-xs font-mono font-semibold text-indigo-400 mb-1 mt-5">{name}</div>
      <table className="w-full text-xs font-mono border border-gray-800">
        <thead>
          <tr className="border-b border-gray-700 bg-gray-900">
            {columns.map(col => (
              <th key={col} className="text-gray-500 px-2 py-0.5 text-left font-normal">{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-gray-800">
              {row.map((val, j) => (
                <td key={j} className="text-gray-200 px-2 py-0.5 break-all">{fmtVal(val)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SongCard({ song }: { song: Song }) {
  const [expanded, setExpanded] = useState(false);
  const dsp = song.dsp_features;
  const profile = song.ml_profile;
  const moods = song.ml_moods;
  const file = song.file_metadata;
  const track = song.track_metadata;

  return (
    <div className="border border-gray-800 rounded-lg overflow-hidden bg-gray-900/30">
      <button
        className="w-full flex items-center gap-4 px-4 py-3 hover:bg-gray-800/50 transition-colors text-left"
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

      {expanded && (
        <div className="border-t border-gray-800 px-4 py-4">

          <KVTable name="songs" rows={[
            ['id', song.id],
            ['title', song.title],
            ['artist', song.artist],
          ]} />

          {file && (
            <KVTable name="file_metadata" rows={[
              ['file_format', file.file_format],
              ['duration_seconds', file.duration_seconds],
              ['sample_rate_hz', file.sample_rate_hz],
              ['bitrate_kbps', file.bitrate_kbps],
              ['channels', file.channels],
            ]} />
          )}

          {track && (
            <KVTable name="track_metadata" rows={[
              ['release_date', track.release_date],
              ['playcount', track.playcount],
              ['listeners', track.listeners],
              ['mbid', track.mbid],
              ['album_mbid', track.album_mbid],
              ['url', track.url],
              ['mb_genres', track.mb_genres],
              ['featured_artists', track.featured_artists],
            ]} />
          )}

          {track?.similar_tracks && track.similar_tracks.length > 0 && (
            <MultiTable
              name="track_metadata → similar_tracks"
              columns={['title', 'artist', 'similarity']}
              rows={track.similar_tracks.map(t => [t.title, t.artist, t.similarity])}
            />
          )}

          {dsp && (
            <KVTable name="dsp_features" rows={[
              ['bpm', dsp.bpm],
              ['beat_count', dsp.beat_count],
              ['beat_confidence', dsp.beat_confidence],
              ['danceability', dsp.danceability],
              ['beat_loudness_mean', dsp.beat_loudness_mean],
              ['onset_rate', dsp.onset_rate],
              ['key', dsp.key],
              ['scale', dsp.scale],
              ['key_strength', dsp.key_strength],
              ['tuning_frequency_hz', dsp.tuning_frequency_hz],
              ['tuning_cents_deviation', dsp.tuning_cents_deviation],
              ['most_common_chord', dsp.most_common_chord],
              ['chord_strength_mean', dsp.chord_strength_mean],
              ['chord_change_rate', dsp.chord_change_rate],
              ['integrated_lufs', dsp.integrated_lufs],
              ['loudness_range_lu', dsp.loudness_range_lu],
              ['dynamic_complexity', dsp.dynamic_complexity],
              ['loudness_db', dsp.loudness_db],
              ['spectral_centroid_mean', dsp.spectral_centroid_mean],
              ['spectral_rolloff_mean', dsp.spectral_rolloff_mean],
              ['spectral_flux_mean', dsp.spectral_flux_mean],
              ['mfcc_mean', dsp.mfcc_mean],
              ['zero_crossing_rate', dsp.zero_crossing_rate],
              ['dissonance', dsp.dissonance],
            ]} />
          )}

          {profile && (
            <KVTable name="ml_profile_features" rows={[
              ['approachability_label', profile.approachability_label],
              ['approachability_score', profile.approachability_score],
              ['engagement_label', profile.engagement_label],
              ['engagement_score', profile.engagement_score],
              ['voice_label', profile.voice_label],
              ['voice_score', profile.voice_score],
              ['gender_label', profile.gender_label],
              ['gender_score', profile.gender_score],
              ['arousal', profile.arousal],
              ['valence', profile.valence],
            ]} />
          )}

          {moods && (
            <KVTable name="ml_mood_features" rows={[
              ['happy', moods.happy],
              ['sad', moods.sad],
              ['aggressive', moods.aggressive],
              ['party', moods.party],
              ['relaxed', moods.relaxed],
              ['acoustic', moods.acoustic],
              ['electronic', moods.electronic],
            ]} />
          )}

          {song.parent_genres.length > 0 && (
            <MultiTable
              name="parent_genres"
              columns={['genre', 'percentage']}
              rows={[...song.parent_genres]
                .sort((a, b) => b.percentage - a.percentage)
                .map(pg => [pg.genre, pg.percentage])}
            />
          )}

          {song.detailed_genres.length > 0 && (
            <MultiTable
              name="detailed_genres"
              columns={['genre', 'probability']}
              rows={[...song.detailed_genres]
                .sort((a, b) => b.probability - a.probability)
                .map(dg => [dg.genre, dg.probability])}
            />
          )}

          {song.instruments.length > 0 && (
            <MultiTable
              name="instruments"
              columns={['instrument', 'probability']}
              rows={[...song.instruments]
                .sort((a, b) => b.probability - a.probability)
                .map(inst => [inst.instrument, inst.probability])}
            />
          )}
        </div>
      )}
    </div>
  );
}
