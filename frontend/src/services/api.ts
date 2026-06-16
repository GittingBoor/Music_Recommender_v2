import type { Song } from "../types/song";
import type { UmapResponse } from "../types/umap";
import type { CorrelationResponse, TimeseriesResponse, SongDetail } from "../types/analysis";

export async function fetchSongs(): Promise<Song[]> {
  const res = await fetch("/api/songs");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchUmap(features?: string[]): Promise<UmapResponse> {
  const params =
    features && features.length > 0 ? `?features=${features.join(",")}` : "";
  const res = await fetch(`/api/umap${params}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchCorrelations(): Promise<CorrelationResponse> {
  const res = await fetch("/api/analysis/correlations");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchTimeseries(
  feature: string,
  mood: string | null,
  threshold: number,
  songId: string | null,
): Promise<TimeseriesResponse> {
  const params = new URLSearchParams({ feature, threshold: String(threshold) });
  if (mood) params.set("mood", mood);
  if (songId) params.set("song_id", songId);
  const res = await fetch(`/api/analysis/timeseries?${params}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchSongDetail(songId: string): Promise<SongDetail> {
  const res = await fetch(`/api/analysis/song/${songId}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
