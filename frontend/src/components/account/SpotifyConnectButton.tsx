import { spotifyConnectUrl } from "../../services/api";

/** Full-page navigation into Spotify's OAuth flow; the callback returns to `next`. */
export function SpotifyConnectButton({ next, label = "Spotify verbinden" }: {
  readonly next: string;
  readonly label?: string;
}) {
  return (
    <a href={spotifyConnectUrl(next)} className="btn btn-primary h-8 px-3">
      {label}
    </a>
  );
}
