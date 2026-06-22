/**
 * Global single-player singleton.
 * Only one song plays at a time across the whole app.
 * Designed for use with React's useSyncExternalStore.
 *
 * Note: subscribe/getSnapshot only fire on play-state changes (not every
 * timeupdate tick) so that PlayButton components don't re-render constantly.
 * PlayerBar attaches its own timeupdate listener via getAudio().
 */

export interface PlayerSnapshot {
  currentId: string | null;
  playing: boolean;
}

type Listener = () => void;

let _audio: HTMLAudioElement | null = null;
let _state: PlayerSnapshot = { currentId: null, playing: false };
const _listeners = new Set<Listener>();

function _getAudio(): HTMLAudioElement {
  if (!_audio) {
    _audio = new Audio();
    _audio.addEventListener("play",  () => _emit({ ..._state, playing: true  }));
    _audio.addEventListener("pause", () => _emit({ ..._state, playing: false }));
    _audio.addEventListener("ended", () => _emit({ currentId: null, playing: false }));
    _audio.addEventListener("error", () => _emit({ currentId: null, playing: false }));
  }
  return _audio;
}

function _emit(next: PlayerSnapshot): void {
  _state = next;
  for (const l of _listeners) l();
}

/** Toggle play/pause for the given song. Starting a different song stops the previous one. */
export function toggle(songId: string): void {
  const audio = _getAudio();

  if (_state.currentId === songId) {
    if (_state.playing) {
      audio.pause();
    } else {
      audio.play().catch(() => _emit({ currentId: null, playing: false }));
    }
  } else {
    audio.pause();
    audio.src = `/api/audio/full/${songId}`;
    audio.currentTime = 0;
    _emit({ currentId: songId, playing: false });
    audio.play().catch(() => _emit({ currentId: null, playing: false }));
  }
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

/** Subscribe to play-state changes (for useSyncExternalStore). */
export function subscribe(listener: Listener): () => void {
  _listeners.add(listener);
  return () => _listeners.delete(listener);
}

/** Snapshot getter (stable reference for useSyncExternalStore). */
export function getSnapshot(): PlayerSnapshot {
  return _state;
}
