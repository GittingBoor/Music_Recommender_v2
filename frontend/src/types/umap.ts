export interface UmapPoint2D {
  song_id: string;
  x: number;
  y: number;
  title: string | null;
  artist: string | null;
}

export interface UmapPoint3D {
  song_id: string;
  x: number;
  y: number;
  z: number;
  title: string | null;
  artist: string | null;
}

export interface UmapResponse {
  points_2d: UmapPoint2D[];
  points_3d: UmapPoint3D[];
  features_used: string[];
}
