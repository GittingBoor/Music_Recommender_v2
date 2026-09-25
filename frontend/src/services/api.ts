import type { Song } from "../types/song";
import type { UmapResponse } from "../types/umap";
import type { CorrelationResponse, TimeAxisMode, TimeseriesResponse, SongDetail } from "../types/analysis";

export async function fetchSongs(): Promise<Song[]> {
  const res = await fetch("/api/songs");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchSongCount(): Promise<number> {
  const res = await fetch("/api/songs/count");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data: { count: number } = await res.json();
  return data.count;
}

/**
 * Songs most similar to the given one, closest first. Uses all audio features
 * and is independent of the UMAP view's axis selection.
 */
export async function fetchNeighbors(songId: string): Promise<string[]> {
  const res = await fetch(`/api/songs/${songId}/neighbors`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data: { neighbors: string[] } = await res.json();
  return data.neighbors;
}

export async function fetchUmap(features?: string[]): Promise<UmapResponse> {
  const params =
    features && features.length > 0 ? `?features=${features.join(",")}` : "";
  const res = await fetch(`/api/umap${params}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export interface PreviewSegment {
  start_seconds: number;
  duration_seconds: number;
}

/** The most recognisable segment (chorus) of a song, located from its DSP timeseries. */
export async function fetchPreviewSegment(songId: string): Promise<PreviewSegment> {
  const res = await fetch(`/api/audio/preview/${songId}`);
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
  mode: TimeAxisMode,
): Promise<TimeseriesResponse> {
  const params = new URLSearchParams({ feature, threshold: String(threshold), mode });
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

/** A classified YouTube failure with a reason the user can act on. */
export interface YoutubeErrorDetail {
  kind: string;
  title: string;
  explanation: string;
  /** "video" = only this clip, "global" = every download is affected. */
  scope: string;
  raw_message: string;
}

/** Thrown by the YouTube calls so callers can show the explanation. */
export class YoutubeRequestError extends Error {
  readonly detail: YoutubeErrorDetail;

  constructor(detail: YoutubeErrorDetail) {
    super(detail.title);
    this.name = "YoutubeRequestError";
    this.detail = detail;
  }
}

function fallbackDetail(message: string): YoutubeErrorDetail {
  return {
    kind: "unknown",
    title: "Anfrage fehlgeschlagen",
    explanation:
      "Der Server hat nicht wie erwartet geantwortet. Läuft das Backend? " +
      "Prüfe die Container mit `docker-compose ps`.",
    scope: "global",
    raw_message: message,
  };
}

/** Turn a failed response into a YoutubeRequestError carrying the server's explanation. */
async function youtubeError(res: Response): Promise<YoutubeRequestError> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (detail && typeof detail === "object" && "explanation" in detail) {
      return new YoutubeRequestError(detail as YoutubeErrorDetail);
    }
    if (typeof detail === "string") {
      return new YoutubeRequestError({
        kind: "invalid_input",
        title: "Eingabe nicht verwertbar",
        explanation: detail,
        scope: "video",
        raw_message: detail,
      });
    }
  } catch {
    // fall through to the generic detail below
  }
  return new YoutubeRequestError(fallbackDetail(`HTTP ${res.status}`));
}

export interface UploadResult {
  status: "saved" | "skipped" | "error";
  reason: string | null;
  title: string | null;
  artist: string | null;
  song_id: string | null;
  filename: string;
  error?: YoutubeErrorDetail | null;
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
  /** Title and artist of a library song were found in this video's title/channel. */
  in_library: boolean;
}

export async function searchYoutube(
  q: string,
  limit = 10,
): Promise<YoutubeSearchItem[]> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  const res = await fetch(`/api/youtube/search?${params}`);
  if (!res.ok) throw await youtubeError(res);
  return res.json();
}

export interface YoutubeSearchResultsEvent {
  type: "results";
  items: YoutubeSearchItem[];
}

export interface YoutubeSearchRejectedEvent {
  type: "rejected";
  video_id: string;
}

export interface YoutubeSearchDoneEvent {
  type: "done";
}

export type YoutubeSearchEvent =
  | YoutubeSearchResultsEvent
  | YoutubeSearchRejectedEvent
  | YoutubeSearchDoneEvent;

/**
 * Streaming music search: every plausible hit arrives at once, then
 * "rejected" events remove hits YouTube confirms are not music.
 */
export async function streamYoutubeSearch(
  q: string,
  limit: number,
  onEvent: (event: YoutubeSearchEvent) => void,
): Promise<void> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  const res = await fetch(`/api/youtube/search/stream?${params}`);
  if (!res.ok) throw await youtubeError(res);
  if (!res.body) throw new YoutubeRequestError(fallbackDetail("Search response has no body to stream"));

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line) as YoutubeSearchEvent);
    }
  }
}

export interface YoutubePlaylistHit {
  playlist_id: string;
  title: string;
  uploader: string | null;
  thumbnail: string | null;
  url: string;
}

/** Playlists matching a search; open one with fetchYoutubePlaylist(hit.url). */
export async function searchYoutubePlaylists(
  q: string,
  limit = 3,
): Promise<YoutubePlaylistHit[]> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  const res = await fetch(`/api/youtube/playlists/search?${params}`);
  if (!res.ok) throw await youtubeError(res);
  return res.json();
}

/** Random music videos that aren't in the library yet — shown before searching. */
export async function fetchYoutubeExamples(limit = 5): Promise<YoutubeSearchItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`/api/youtube/examples?${params}`);
  if (!res.ok) throw await youtubeError(res);
  return res.json();
}

export interface YoutubePlaylist {
  title: string | null;
  items: YoutubeSearchItem[];
}

/** Resolve a playlist URL into its music videos. */
export async function fetchYoutubePlaylist(
  url: string,
  limit = 50,
): Promise<YoutubePlaylist> {
  const params = new URLSearchParams({ url, limit: String(limit) });
  const res = await fetch(`/api/youtube/playlist?${params}`);
  if (!res.ok) throw await youtubeError(res);
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

// ── ingest pipeline ─────────────────────────────────────────────────────────

export type PipelineStage =
  | "queued" | "searching" | "downloading" | "trimming" | "waiting" | "analyzing";

export interface PipelineJob {
  id: number;
  /** "upload" | "youtube" | "bulk" */
  source: string;
  label: string;
  stage: PipelineStage;
  seconds_in_stage: number;
}

/** Every song the backend is still working on, running ones first. */
export async function fetchPipeline(): Promise<PipelineJob[]> {
  const res = await fetch("/api/ingest/pipeline");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()).jobs;
}
