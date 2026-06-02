import type { Song } from '../types/song';

export async function fetchSongs(): Promise<Song[]> {
  const res = await fetch('/api/songs');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
