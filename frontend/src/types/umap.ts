export interface UmapPoint2D {
  song_id: string;
  x: number;
  y: number;
  title: string | null;
  artist: string | null;
}

export interface UmapResponse {
  points_2d: UmapPoint2D[];
  features_used: string[];
}
