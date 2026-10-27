import type { Song } from "../types/song";
import type { UmapResponse, UmapStatus } from "../types/umap";
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

export async function fetchUmapStatus(): Promise<UmapStatus> {
  const res = await fetch("/api/umap/status");
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
  songIds: string[],
  mode: TimeAxisMode,
): Promise<TimeseriesResponse> {
  const params = new URLSearchParams({ feature, threshold: String(threshold), mode });
  if (mood) params.set("mood", mood);
  for (const id of songIds) params.append("song_id", id);
  const res = await fetch(`/api/analysis/timeseries?${params}`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : null;
    throw new Error(detail ? `HTTP ${res.status} — ${detail}` : `HTTP ${res.status}`);
  }
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

/** Title/artist typed in by the uploader for a file nobody could identify. */
export interface SongIdentityInput {
  readonly title: string;
  readonly artist: string;
}

export async function uploadSong(file: File, identity?: SongIdentityInput): Promise<UploadResult> {
  const fd = new FormData();
  fd.append("file", file);
  if (identity) {
    fd.append("title", identity.title);
    fd.append("artist", identity.artist);
  }
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

export type YoutubeStage = PipelineStage | "done";

export interface YoutubeDownloadStatus {
  job_id: number;
  stage: YoutubeStage;
  progress: number; // 0..1
  /** Set once the job is finished; same shape as an upload result. */
  result: UploadResult | null;
}

/**
 * Queue a video for download, trimming and analysis; returns its job id.
 * `query` is the "Artist - Title" search that found the video; the server
 * names the song after it when the video title does not name the artist.
 */
export async function enqueueYoutubeDownload(item: YoutubeSearchItem, query: string | null = null): Promise<number> {
  const res = await fetch("/api/youtube/downloads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: item.video_id, title: item.title, uploader: item.uploader, query }),
  });
  if (!res.ok) throw await youtubeError(res);
  return (await res.json()).job_id;
}

/** Current state of queued downloads. */
export async function fetchYoutubeDownloads(jobIds: readonly number[]): Promise<YoutubeDownloadStatus[]> {
  const params = new URLSearchParams();
  for (const id of jobIds) params.append("ids", String(id));
  const res = await fetch(`/api/youtube/downloads?${params}`);
  if (!res.ok) throw await youtubeError(res);
  return res.json();
}

// ── ingest pipeline ─────────────────────────────────────────────────────────

export type PipelineStage =
  | "queued" | "searching" | "downloading" | "trimming" | "waiting" | "analyzing";

export interface PipelineJob {
  id: number;
  /** "upload" | "youtube" | "bulk" | "spotify" */
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

// ── account and spotify ─────────────────────────────────────────────────────

/** A failed account/Spotify request; `message` is the server's German explanation. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const INVALID_INPUT_MESSAGE = "Die Eingabe wurde nicht angenommen. Bitte prüfe deine Angaben.";

/** `{detail: string}` becomes the message; pydantic's `{detail: [...]}` a generic hint. */
async function apiError(res: Response): Promise<ApiError> {
  try {
    const body: unknown = await res.json();
    const detail = typeof body === "object" && body !== null && "detail" in body ? body.detail : undefined;
    if (typeof detail === "string") return new ApiError(res.status, detail);
    if (Array.isArray(detail)) return new ApiError(res.status, INVALID_INPUT_MESSAGE);
  } catch {
    // not JSON — fall through to the status-only message
  }
  return new ApiError(res.status, `Der Server hat mit HTTP ${res.status} geantwortet. Bitte später erneut versuchen.`);
}

async function sendJson(method: string, url: string, body?: object): Promise<Response> {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw await apiError(res);
  return res;
}

export interface SpotifyConnection {
  readonly spotify_user_id: string;
  readonly display_name: string | null;
}

export interface Account {
  readonly email: string;
  readonly spotify: SpotifyConnection | null;
}

export interface Credentials {
  readonly email: string;
  readonly password: string;
}

/** The logged-in account, or null without a valid login cookie. */
export async function fetchAccount(): Promise<Account | null> {
  const res = await fetch("/api/account/me");
  if (res.status === 401) return null;
  if (!res.ok) throw await apiError(res);
  return res.json();
}

export async function registerAccount(credentials: Credentials): Promise<Account> {
  return (await sendJson("POST", "/api/account/register", credentials)).json();
}

export async function loginAccount(credentials: Credentials): Promise<Account> {
  return (await sendJson("POST", "/api/account/login", credentials)).json();
}

export async function logoutAccount(): Promise<void> {
  await sendJson("POST", "/api/account/logout");
}

/** Always succeeds, whether or not an account exists for the address. */
export async function requestPasswordReset(email: string): Promise<void> {
  await sendJson("POST", "/api/account/forgot-password", { email });
}

/** Sets the new password and logs the account in (cookie). */
export async function resetPassword(token: string, password: string): Promise<void> {
  await sendJson("POST", "/api/account/reset-password", { token, password });
}

/** Full-page target that starts the Spotify OAuth flow and returns to `next`. */
export function spotifyConnectUrl(next: string): string {
  return `/api/spotify/connect?next=${encodeURIComponent(next)}`;
}

export async function disconnectSpotify(): Promise<void> {
  await sendJson("DELETE", "/api/spotify/connection");
}

export interface SpotifyPlaylist {
  readonly id: string;
  readonly name: string;
  readonly image: string | null;
  readonly track_count: number;
  readonly owner: string | null;
  readonly last_import_id: number | null;
}

/** 409: not connected or the connection expired; 403: account not allowlisted. */
export async function fetchSpotifyPlaylists(): Promise<SpotifyPlaylist[]> {
  return (await sendJson("GET", "/api/spotify/playlists")).json();
}

export interface SpotifyImport {
  readonly id: number;
  readonly playlist_id: string;
  readonly name: string;
  readonly created_at: string;
  /** When the last track left the queue; null while the import still runs. */
  readonly finished_at: string | null;
  /** True when old tracks lack an end time: finished_at is then a lower bound. */
  readonly finished_estimated: boolean;
  readonly total: number;
  readonly saved: number;
  readonly duplicate: number;
  readonly failed: number;
  readonly queued: number;
}

export type SpotifyTrackStatus = "queued" | "saved" | "duplicate" | "failed";

export interface SpotifyImportTrack {
  readonly position: number;
  readonly title: string;
  readonly artists: readonly string[];
  readonly status: SpotifyTrackStatus;
  readonly reason: string | null;
  readonly song_id: string | null;
}

export interface SpotifyImportDetail extends SpotifyImport {
  readonly tracks: readonly SpotifyImportTrack[];
}

export async function importSpotifyPlaylist(playlistId: string): Promise<SpotifyImport> {
  return (await sendJson("POST", `/api/spotify/playlists/${encodeURIComponent(playlistId)}/import`)).json();
}

/** Re-queues the import's failed tracks. 409: nothing failed; 503: AcoustID key missing. */
export async function retrySpotifyImport(importId: number): Promise<SpotifyImport> {
  return (await sendJson("POST", `/api/spotify/imports/${importId}/retry`)).json();
}

/** The account's imports, newest first. */
export async function fetchSpotifyImports(): Promise<SpotifyImport[]> {
  return (await sendJson("GET", "/api/spotify/imports")).json();
}

export async function fetchSpotifyImport(importId: number): Promise<SpotifyImportDetail> {
  return (await sendJson("GET", `/api/spotify/imports/${importId}`)).json();
}

/** One of the account's playlists as a view on the library (or "liked": the saved tracks). */
export interface MyPlaylist {
  readonly id: number;
  readonly spotify_playlist_id: string;
  readonly kind: "playlist" | "liked";
  readonly name: string;
  readonly image: string | null;
  /** Distinct tracks on Spotify; song_ids are the ones in the library, in playlist order. */
  readonly track_count: number;
  readonly synced_at: string;
  readonly song_ids: readonly string[];
}

export interface MyPlaylistsSync {
  readonly playlists: readonly MyPlaylist[];
  /** The connection lacks the saved-tracks permission; reconnecting Spotify grants it. */
  readonly liked_needs_reconnect: boolean;
}

/** Playlists as last synced or imported; empty when logged out. */
export async function fetchMyPlaylists(): Promise<MyPlaylist[]> {
  return (await sendJson("GET", "/api/spotify/library")).json();
}

/** Reads every playlist and the saved tracks from Spotify again. 409: not connected / expired. */
export async function syncMyPlaylists(): Promise<MyPlaylistsSync> {
  return (await sendJson("POST", "/api/spotify/library/sync")).json();
}
