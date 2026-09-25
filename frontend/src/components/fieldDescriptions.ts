/**
 * One-sentence explanations for every value shown in an expanded SongCard,
 * keyed by "<table>.<column>".
 */
export const FIELD_DESCRIPTIONS: Readonly<Record<string, string>> = {
  // songs
  'songs.id': 'Internal unique identifier of the song in the database.',
  'songs.title': 'Song title, taken from AcoustID/MusicBrainz or the file tags.',
  'songs.artist': 'Performing artist, taken from AcoustID/MusicBrainz or the file tags.',

  // file_metadata
  'file_metadata.filename': 'Name of the audio file the analysis was run on.',
  'file_metadata.file_format': 'Container/codec of the audio file, e.g. mp3 or flac.',
  'file_metadata.duration_seconds': 'Length of the audio file in seconds.',
  'file_metadata.sample_rate_hz': 'Number of audio samples per second stored in the file.',
  'file_metadata.bitrate_kbps': 'Amount of data per second of audio; higher usually means better quality.',
  'file_metadata.channels': 'Number of audio channels (1 = mono, 2 = stereo).',

  // track_metadata
  'track_metadata.release_date': 'Earliest known release date from Spotify or MusicBrainz.',
  'track_metadata.playcount': 'Total number of plays recorded on Last.fm.',
  'track_metadata.listeners': 'Number of distinct Last.fm users who listened to the track.',
  'track_metadata.mbid': 'MusicBrainz ID of this recording.',
  'track_metadata.album_mbid': 'MusicBrainz ID of the album the recording appears on.',
  'track_metadata.url': 'Link to the track page on Last.fm.',
  'track_metadata.mb_genres': 'Genre tags the MusicBrainz community assigned to the recording.',
  'track_metadata.featured_artists': 'Additional artists credited on the track.',
  'track_metadata.similar_tracks.title': 'Title of a track Last.fm considers similar.',
  'track_metadata.similar_tracks.artist': 'Artist of the similar track.',
  'track_metadata.similar_tracks.similarity': 'How similar Last.fm rates the track, from 0 to 1.',

  // dsp_features
  'dsp_features.bpm': 'Estimated tempo in beats per minute.',
  'dsp_features.beat_count': 'Number of beats detected across the whole song.',
  'dsp_features.beat_confidence': 'How reliable the beat tracking is, from 0 to about 5.3 (above 3.5 is very reliable).',
  'dsp_features.danceability': 'How suitable the rhythm is for dancing, from 0 to 1, computed from beat regularity.',
  'dsp_features.beat_loudness_mean': 'Average loudness of the audio at the detected beat positions.',
  'dsp_features.onset_rate': 'Number of note or sound onsets per second, a rough measure of rhythmic density.',
  'dsp_features.key': 'Estimated root note of the musical key.',
  'dsp_features.scale': 'Whether the key is major or minor.',
  'dsp_features.key_strength': 'How clearly the music fits the detected key, from 0 to 1.',
  'dsp_features.tuning_frequency_hz': 'Estimated reference pitch of the note A (standard tuning is 440 Hz).',
  'dsp_features.tuning_cents_deviation': 'How far the tuning deviates from 440 Hz, in cents (100 cents = one semitone).',
  'dsp_features.most_common_chord': 'Chord that is detected most often throughout the song.',
  'dsp_features.chord_strength_mean': 'Average confidence of the chord detection, from 0 to 1.',
  'dsp_features.chord_change_rate': 'Share of analysis frames in which the chord changes, from 0 to 1.',
  'dsp_features.integrated_lufs': 'Overall perceived loudness per the EBU R128 standard; closer to 0 means louder.',
  'dsp_features.loudness_range_lu': 'Spread between quiet and loud passages in loudness units; higher means more dynamic.',
  'dsp_features.dynamic_complexity': 'Average amount of loudness fluctuation in dB; higher means more dynamic changes.',
  'dsp_features.loudness_db': 'Overall loudness estimate in dB used for the dynamic complexity calculation.',
  'dsp_features.spectral_centroid_mean': 'Average "center of mass" of the frequency spectrum in Hz; higher sounds brighter.',
  'dsp_features.spectral_rolloff_mean': 'Frequency below which most of the energy lies, on average; higher sounds brighter.',
  'dsp_features.spectral_flux_mean': 'How quickly the spectrum changes from frame to frame on average.',
  'dsp_features.mfcc_mean': 'Average of 13 MFCC coefficients, a compact fingerprint of the overall timbre.',
  'dsp_features.zero_crossing_rate': 'How often the waveform crosses zero; higher values suggest noisier or percussive sound.',
  'dsp_features.dissonance': 'Perceived roughness of the sound, from 0 (consonant) to 1 (dissonant).',

  // ml_profile_features
  'ml_profile_features.niche_score': 'Model probability that the song appeals to a niche audience.',
  'ml_profile_features.mainstream_score': 'Model probability that the song appeals to a mainstream audience.',
  'ml_profile_features.background_score': 'Model probability that the song works as background music.',
  'ml_profile_features.active_score': 'Model probability that the song invites active, attentive listening.',
  'ml_profile_features.instrumental_score': 'Model probability that the song has no vocals.',
  'ml_profile_features.vocal_score': 'Model probability that the song contains vocals.',
  'ml_profile_features.female_score': 'Model probability that the dominant voice is female.',
  'ml_profile_features.male_score': 'Model probability that the dominant voice is male.',
  'ml_profile_features.arousal': 'Predicted energy/intensity on a 1–9 scale (DEAM model).',
  'ml_profile_features.valence': 'Predicted positivity of the mood on a 1–9 scale (DEAM model).',

  // ml_mood_features
  'ml_mood_features.happy': 'Model probability that the song sounds happy.',
  'ml_mood_features.sad': 'Model probability that the song sounds sad.',
  'ml_mood_features.aggressive': 'Model probability that the song sounds aggressive.',
  'ml_mood_features.party': 'Model probability that the song sounds like party music.',
  'ml_mood_features.relaxed': 'Model probability that the song sounds relaxed.',
  'ml_mood_features.acoustic': 'Model probability that the song is played on acoustic instruments.',
  'ml_mood_features.electronic': 'Model probability that the song is electronically produced.',

  // other_features
  'other_features.gmbi_valence': 'GMBI branding model: how positive the song feels.',
  'other_features.gmbi_arousal': 'GMBI branding model: how energetic the song feels.',
  'other_features.gmbi_authenticity': 'GMBI branding model: how genuine and authentic the song feels.',
  'other_features.gmbi_timeliness': 'GMBI branding model: how contemporary the song feels.',
  'other_features.gmbi_complexity': 'GMBI branding model: how complex the song feels.',
  'other_features.tonal': 'Model probability that the music is tonal rather than atonal.',
  'other_features.tonal_timeseries': 'Tonal probability over the course of the song, one value per analysis window.',
  'other_features.hpcp_mean': 'Average strength of the 12 pitch classes (chroma), starting at A.',
  'other_features.tristimulus_mean': 'Average energy share of the fundamental, harmonics 2–4 and higher harmonics, describing timbre.',

  // genre / instrument tables
  'parent_genres.genre': 'Top-level genre from the Discogs taxonomy.',
  'parent_genres.percentage': 'Share of this top-level genre in the song, in percent.',
  'detailed_genres.genre': 'Detailed Discogs style predicted for the song.',
  'detailed_genres.probability': 'Model probability for this style, from 0 to 1.',
  'instruments.instrument': 'Instrument the model detected in the song.',
  'instruments.probability': 'Model probability that the instrument is present, from 0 to 1.',
};
