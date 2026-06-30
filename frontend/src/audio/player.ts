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
}

type Listener = () => void;

const DEFAULT_VOLUME = 1;
/** Seconds into a track after which "previous" restarts it instead of going back. */
const PREVIOUS_RESTART_THRESHOLD_S = 3;

let _audio: HTMLAudioElement | null = null;
let _queue: string[] = [];
let _state: PlayerSnapshot = { currentId: null, playing: false, volume: DEFAULT_VOLUME };
const _listeners = new Set<Listener>();

function _getAudio(): HTMLAudioElement {
  if (!_audio) {
    _audio = new Audio();
    _audio.volume = _state.volume;
    _audio.addEventListener("play",  () => _emit({ ..._state, playing: true  }));
    _audio.addEventListener("pause", () => _emit({ ..._state, playing: false }));
    _audio.addEventListener("ended", () => next());
    _audio.addEventListener("error", () => _emit({ ..._state, currentId: null, playing: false }));
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
  _emit({ ..._state, currentId: songId, playing: false });
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

/** Advance to the next song in the queue, wrapping around at the end. */
export function next(): void {
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
  _emit({ ..._state, currentId: null, playing: false });
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
