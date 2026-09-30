export interface UmapPoint2D {
  song_id: string;
  x: number;
  y: number;
  title: string | null;
  artist: string | null;
  /** Nearest neighbours in the high-dimensional feature space, closest first. */
  neighbors: string[];
}

/** Progress of the server-side UMAP fit. */
export interface UmapStatus {
  phase: "empty" | "fitting" | "ready";
  elapsed_seconds: number;
  /** Duration of the previous fit (a fixed guess before the first one). */
  estimated_seconds: number;
  song_count: number;
}

export interface UmapResponse {
  points_2d: UmapPoint2D[];
  features_used: string[];
}
