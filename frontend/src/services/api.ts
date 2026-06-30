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

export interface UploadResult {
  status: "saved" | "skipped" | "error";
  reason: string | null;
  title: string | null;
  artist: string | null;
  song_id: string | null;
  filename: string;
}

export async function uploadSong(file: File): Promise<UploadResult> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body: fd });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export interface YoutubeSearchItem {
  video_id: string;
  title: string;
  uploader: string | null;
  duration: number | null;
  thumbnail: string | null;
  url: string;
}

export async function searchYoutube(
  q: string,
  limit = 10,
): Promise<YoutubeSearchItem[]> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  const res = await fetch(`/api/youtube/search?${params}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export type YoutubeStage = "downloading" | "trimming" | "analyzing" | "done";

export interface YoutubeProgress {
  stage: YoutubeStage;
  progress: number; // 0..1
}

/**
 * Download a video, trim it and run analysis on the backend, streaming
 * progress events. Resolves with the final UploadResult once it's in the DB.
 */
export async function downloadYoutube(
  videoId: string,
  title: string | undefined,
  onProgress: (p: YoutubeProgress) => void,
): Promise<UploadResult> {
  const res = await fetch("/api/youtube/download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId, title: title ?? null }),
  });
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: UploadResult | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const evt = JSON.parse(line) as YoutubeProgress & { result?: UploadResult };
      onProgress({ stage: evt.stage, progress: evt.progress });
      if (evt.result) result = evt.result;
    }
  }

  if (!result) throw new Error("No result received from server");
  return result;
}
