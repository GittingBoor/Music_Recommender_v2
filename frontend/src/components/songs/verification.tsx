import type { MetadataSource, Song } from "../../types/song";

export type VerificationStatus = "acoustid" | "reviewed" | "unverified";

interface StatusInfo {
  readonly short: string;
  readonly label: string;
  readonly dotClass: string;
  readonly textClass: string;
}

const STATUS_INFO: Readonly<Record<VerificationStatus, StatusInfo>> = {
  acoustid: {
    short: "Verified",
    label: "Verified via AcoustID fingerprint",
    dotClass: "bg-ok",
    textClass: "text-ok",
  },
  reviewed: {
    short: "Reviewed",
    label: "Reviewed by admin",
    dotClass: "bg-ok",
    textClass: "text-ok",
  },
  unverified: {
    short: "Unverified",
    label: "Unverified — name taken from YouTube title or file, not yet reviewed",
    dotClass: "bg-warn",
    textClass: "text-warn",
  },
};

const SOURCE_LABEL: Readonly<Record<MetadataSource, string>> = {
  acoustid: "AcoustID fingerprint",
  youtube_title: "YouTube title",
  user_input: "Entered manually",
  file_tags: "File tags",
};

/** AcoustID match wins over an admin review; anything else may carry a wrong title/artist. */
export function verificationOf(song: Song): VerificationStatus {
  if (song.acoustid_id != null) return "acoustid";
  if (song.metadata_reviewed) return "reviewed";
  return "unverified";
}

export function metadataSourceLabel(source: string | null): string | null {
  if (source == null) return null;
  return source in SOURCE_LABEL ? SOURCE_LABEL[source as MetadataSource] : source;
}

export function youtubeUrl(videoId: string): string {
  return `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}`;
}

/** Square status dot (same shape as the upload page's status dots) with a hover/AT label. */
export function VerificationDot({ song, className = "" }: { song: Song; className?: string }) {
  const info = STATUS_INFO[verificationOf(song)];
  return (
    <span
      role="img"
      aria-label={info.label}
      title={info.label}
      className={`inline-block w-1.5 h-1.5 shrink-0 ${info.dotClass} ${className}`}
    />
  );
}

/** Dot plus a short word, for places with room to spell the status out. */
export function VerificationBadge({ song }: { song: Song }) {
  const info = STATUS_INFO[verificationOf(song)];
  return (
    <span className="inline-flex items-center gap-1.5" title={info.label}>
      <span aria-hidden className={`w-1.5 h-1.5 shrink-0 ${info.dotClass}`} />
      <span className={info.textClass}>{info.short}</span>
      <span className="sr-only">: {info.label}</span>
    </span>
  );
}
