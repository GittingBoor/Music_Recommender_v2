/**
 * Global single-player singleton.
 * Only one song plays at a time across the whole app.
 * Designed for use with React's useSyncExternalStore.
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
    // Same song: toggle pause/resume
    if (_state.playing) {
      audio.pause();
    } else {
      audio.play().catch(() => _emit({ currentId: null, playing: false }));
    }
  } else {
    // Different song: swap source and play
    audio.pause();
    audio.src = `/api/audio/full/${songId}`;
    audio.currentTime = 0;
    _emit({ currentId: songId, playing: false }); // optimistic id update before play fires
    audio.play().catch(() => _emit({ currentId: null, playing: false }));
  }
}

/** Subscribe to state changes (for useSyncExternalStore). */
export function subscribe(listener: Listener): () => void {
  _listeners.add(listener);
  return () => _listeners.delete(listener);
}

/** Snapshot getter (stable reference for useSyncExternalStore). */
export function getSnapshot(): PlayerSnapshot {
  return _state;
}
