/**
 * Global single-player singleton.
 * Only one song plays at a time across the whole app.
 * Designed for use with React's useSyncExternalStore.
 *
 * The player keeps an ordered queue of song IDs (the database order) so it can
 * advance to the next / previous track, auto-continue when a song finishes, and
 * pick a random track. The queue is fed in via setQueue().
 *
 * Note: subscribe/getSnapshot only fire on player-state changes (not every
 * timeupdate tick) so that PlayButton components don't re-render constantly.
 * PlayerBar attaches its own timeupdate listener via getAudio().
 */

export interface PlayerSnapshot {
  currentId: string | null;
  playing: boolean;
  volume: number;
  /** Set while a chorus preview (not the full track) is loaded. */
  previewId: string | null;
  /** When on, the next track is the most similar song instead of the next in order. */
  nnMode: boolean;
}

type Listener = () => void;
/** Resolves a song's most similar songs, closest first. */
type NeighborSource = (songId: string) => Promise<string[]>;

const DEFAULT_VOLUME = 1;
/** Seconds into a track after which "previous" restarts it instead of going back. */
const PREVIOUS_RESTART_THRESHOLD_S = 3;
/** How many recently played songs to avoid when picking a neighbour. */
const RECENT_MEMORY = 10;

let _audio: HTMLAudioElement | null = null;
let _queue: string[] = [];
let _state: PlayerSnapshot = {
  currentId: null,
  playing: false,
  volume: DEFAULT_VOLUME,
  previewId: null,
  nnMode: false,
};
/** Set by the app so the player can look up similar songs without importing the API. */
let _neighborSource: NeighborSource | null = null;
/** Recently played IDs, newest last — keeps the radio from ping-ponging. */
let _recent: string[] = [];
/** Absolute time (s) at which the current preview stops, or null for full playback. */
let _previewEnd: number | null = null;
const _listeners = new Set<Listener>();

function _getAudio(): HTMLAudioElement {
  if (!_audio) {
    _audio = new Audio();
    _audio.volume = _state.volume;
    _audio.addEventListener("play",  () => _emit({ ..._state, playing: true  }));
    _audio.addEventListener("pause", () => _emit({ ..._state, playing: false }));
    _audio.addEventListener("ended", () => next());
    _audio.addEventListener("error", () => _emit({ ..._state, currentId: null, playing: false }));
    _audio.addEventListener("timeupdate", () => {
      if (_previewEnd !== null && _audio!.currentTime >= _previewEnd) {
        _previewEnd = null;
        _audio!.pause();
      }
    });
  }
  return _audio;
}

function _emit(snapshot: PlayerSnapshot): void {
  _state = snapshot;
  for (const l of _listeners) l();
}

/** Load and start the given song, replacing whatever was playing. */
function _play(songId: string): void {
  const audio = _getAudio();
  audio.pause();
  audio.src = `/api/audio/full/${songId}`;
  audio.currentTime = 0;
  _previewEnd = null;
  _remember(songId);
  _emit({ ..._state, currentId: songId, playing: false, previewId: null });
  audio.play().catch(() => _emit({ ..._state, currentId: null, playing: false }));
}

function _remember(songId: string): void {
  _recent = [..._recent.filter((id) => id !== songId), songId].slice(-RECENT_MEMORY);
}

/** Register the lookup used for nearest-neighbour playback. */
export function setNeighborSource(source: NeighborSource): void {
  _neighborSource = source;
}

/** Turn nearest-neighbour playback on or off. */
export function setNnMode(enabled: boolean): void {
  if (!enabled) _recent = _state.currentId ? [_state.currentId] : [];
  _emit({ ..._state, nnMode: enabled });
}

/**
 * Pick the closest neighbour that hasn't just been played.
 * Returns null when there is no usable recommendation.
 */
async function _pickNeighbor(songId: string): Promise<string | null> {
  if (!_neighborSource) return null;
  let neighbors: string[];
  try {
    neighbors = await _neighborSource(songId);
  } catch {
    return null; // fall back to queue order
  }
  const fresh = neighbors.find((id) => !_recent.includes(id));
  return fresh ?? neighbors[0] ?? null;
}

/**
 * Play only the given segment of a song — used for chorus previews.
 * Streams the full file and seeks, so no separate preview file is needed.
 */
export function playPreview(
  songId: string,
  startSeconds: number,
  durationSeconds: number,
): void {
  const audio = _getAudio();
  audio.pause();
  audio.src = `/api/audio/full/${songId}`;
  _previewEnd = startSeconds + durationSeconds;

  const seekToStart = () => {
    audio.currentTime = startSeconds;
    audio.removeEventListener("loadedmetadata", seekToStart);
  };
  audio.addEventListener("loadedmetadata", seekToStart);

  _emit({ ..._state, currentId: songId, playing: false, previewId: songId });
  audio.play().catch(() => _emit({ ..._state, currentId: null, playing: false }));
}

function _indexOfCurrent(): number {
  return _state.currentId ? _queue.indexOf(_state.currentId) : -1;
}

/** Set the ordered queue of song IDs the player advances through. */
export function setQueue(ids: string[]): void {
  _queue = ids;
}

/** Toggle play/pause for the given song. Starting a different song stops the previous one. */
export function toggle(songId: string): void {
  const audio = _getAudio();

  if (_state.currentId === songId) {
    if (_state.playing) {
      audio.pause();
    } else {
      audio.play().catch(() => _emit({ ..._state, currentId: null, playing: false }));
    }
  } else {
    _play(songId);
  }
}

/**
 * Advance to the next song.
 *
 * With nearest-neighbour mode on, that is the most similar song to the current
 * one; otherwise the next entry in the queue. If the recommendation cannot be
 * resolved, playback falls back to queue order rather than stopping.
 */
export function next(): void {
  if (_queue.length === 0) {
    stop();
    return;
  }

  const current = _state.currentId;
  if (_state.nnMode && current) {
    void _pickNeighbor(current).then((neighborId) => {
      if (neighborId) _play(neighborId);
      else _playNextInQueue();
    });
    return;
  }
  _playNextInQueue();
}

function _playNextInQueue(): void {
  if (_queue.length === 0) {
    stop();
    return;
  }
  const idx = _indexOfCurrent();
  const nextIdx = idx < 0 ? 0 : (idx + 1) % _queue.length;
  _play(_queue[nextIdx]);
}

/**
 * Go to the previous song. If the current track has played past a short
 * threshold it restarts instead — matching common music-player behaviour.
 */
export function previous(): void {
  if (_queue.length === 0) return;
  const audio = _getAudio();

  if (audio.currentTime > PREVIOUS_RESTART_THRESHOLD_S) {
    seek(0);
    return;
  }
  const idx = _indexOfCurrent();
  const prevIdx = idx <= 0 ? _queue.length - 1 : idx - 1;
  _play(_queue[prevIdx]);
}

/** Play a random song from the queue (avoiding the current one when possible). */
export function shuffle(): void {
  if (_queue.length === 0) return;
  let idx = Math.floor(Math.random() * _queue.length);
  if (_queue.length > 1 && _queue[idx] === _state.currentId) {
    idx = (idx + 1) % _queue.length;
  }
  _play(_queue[idx]);
}

/** Stop playback entirely and clear the current song (hides the player bar). */
export function stop(): void {
  const audio = _getAudio();
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  _previewEnd = null;
  _recent = [];
  _emit({ ..._state, currentId: null, playing: false, previewId: null });
}

/** Set output volume in the range [0, 1]. */
export function setVolume(volume: number): void {
  const clamped = Math.max(0, Math.min(1, volume));
  if (_audio) _audio.volume = clamped;
  _emit({ ..._state, volume: clamped });
}

/** Seek to an absolute time in seconds. */
export function seek(time: number): void {
  const audio = _getAudio();
  if (audio.src) audio.currentTime = Math.max(0, Math.min(time, audio.duration || 0));
}

/** Skip forward or backward by the given number of seconds. */
export function skip(seconds: number): void {
  const audio = _getAudio();
  if (audio.src) seek(audio.currentTime + seconds);
}

/** Expose the raw audio element so components can attach timeupdate listeners. */
export function getAudio(): HTMLAudioElement | null {
  return _audio;
}

/** Subscribe to player-state changes (for useSyncExternalStore). */
export function subscribe(listener: Listener): () => void {
  _listeners.add(listener);
  return () => _listeners.delete(listener);
}

/** Snapshot getter (stable reference for useSyncExternalStore). */
export function getSnapshot(): PlayerSnapshot {
  return _state;
}
