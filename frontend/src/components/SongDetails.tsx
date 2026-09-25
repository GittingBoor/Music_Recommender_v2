import type { Song } from '../types/song';
import { FIELD_DESCRIPTIONS } from './fieldDescriptions';

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

/** Table names like "track_metadata → similar_tracks" map to "track_metadata.similar_tracks". */
function describe(table: string, column: string): string | undefined {
  return FIELD_DESCRIPTIONS[`${table.replace(' → ', '.')}.${column}`];
}

/** Column name with a one-sentence explanation on hover, keyboard focus or tap. */
function FieldLabel({ label, description }: { label: string; description?: string }) {
  if (!description) return <>{label}</>;
  return (
    <span
      tabIndex={0}
      className="group relative cursor-help underline decoration-dotted decoration-gray-600 underline-offset-2 outline-none focus-visible:text-gray-300"
    >
      {label}
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 bottom-full z-20 mb-1 w-56 md:w-64 rounded-md border border-gray-700 bg-gray-950 px-2 py-1.5 font-sans text-[11px] font-normal leading-snug text-gray-200 opacity-0 shadow-lg transition-opacity duration-100 group-hover:opacity-100 group-focus:opacity-100"
      >
        {description}
      </span>
    </span>
  );
}

function KVTable({ name, rows }: { name: string; rows: Row[] }) {
  return (
    <div>
      <div className="text-xs font-mono font-semibold text-indigo-400 mb-1 mt-5 first:mt-0">{name}</div>
      <table className="w-full text-xs font-mono border border-gray-800">
        <tbody>
          {rows.map(([col, val]) => (
            <tr key={col} className="border-t border-gray-800 first:border-t-0">
              <td className="text-gray-500 px-2 py-0.5 w-32 md:w-52 shrink-0 align-top select-all break-all md:break-normal">
                <FieldLabel label={col} description={describe(name, col)} />
              </td>
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
              <th key={col} className="text-gray-500 px-2 py-0.5 text-left font-normal">
                <FieldLabel label={col} description={describe(name, col)} />
              </th>
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

/** Full dump of every stored field for one song — shared by the card list
 *  and the expandable rows of the filter results table. */
export function SongDetails({ song }: { song: Song }) {
  const dsp = song.dsp_features;
  const profile = song.ml_profile;
  const moods = song.ml_moods;
  const other = song.other_features;
  const file = song.file_metadata;
  const track = song.track_metadata;

  return (
    <div>

      <KVTable name="songs" rows={[
        ['id', song.id],
        ['title', song.title],
        ['artist', song.artist],
      ]} />

      {file && (
        <KVTable name="file_metadata" rows={[
          ['filename', file.filename],
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
          ['niche_score', profile.niche_score],
          ['mainstream_score', profile.mainstream_score],
          ['background_score', profile.background_score],
          ['active_score', profile.active_score],
          ['instrumental_score', profile.instrumental_score],
          ['vocal_score', profile.vocal_score],
          ['female_score', profile.female_score],
          ['male_score', profile.male_score],
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

      {other && (
        <KVTable name="other_features" rows={[
          ['gmbi_valence', other.gmbi_valence],
          ['gmbi_arousal', other.gmbi_arousal],
          ['gmbi_authenticity', other.gmbi_authenticity],
          ['gmbi_timeliness', other.gmbi_timeliness],
          ['gmbi_complexity', other.gmbi_complexity],
          ['tonal', other.tonal],
          ['tonal_timeseries', other.tonal_timeseries],
          ['hpcp_mean', other.hpcp_mean],
          ['tristimulus_mean', other.tristimulus_mean],
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
  );
}
