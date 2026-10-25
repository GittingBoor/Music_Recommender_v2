import { navigate } from "../router";

// The Spotify OAuth callback redirects back with ?spotify=<outcome>.

export type NoticeTone = "ok" | "bad";

export interface Notice {
  readonly tone: NoticeTone;
  readonly text: string;
}

const SPOTIFY_NOTICES: Readonly<Record<string, Notice>> = {
  connected:   { tone: "ok",  text: "Spotify ist verbunden." },
  denied:      { tone: "bad", text: "Du hast die Verbindung bei Spotify abgelehnt." },
  not_allowed: {
    tone: "bad",
    text: "Dieser Spotify-Account ist für die App noch nicht freigeschaltet. Benni muss ihn im Spotify-Dashboard eintragen.",
  },
  error:       { tone: "bad", text: "Die Verbindung mit Spotify hat nicht geklappt. Bitte nochmal versuchen." },
  login:       { tone: "bad", text: "Bitte zuerst anmelden." },
};

/** The notice for the `spotify` query param, if any. Pure: safe in a state initializer. */
export function readSpotifyNotice(): Notice | null {
  const outcome = new URLSearchParams(window.location.search).get("spotify");
  if (outcome === null) return null;
  return SPOTIFY_NOTICES[outcome] ?? SPOTIFY_NOTICES.error;
}

/** Removes the `spotify` query param, so a reload does not show the notice again. */
export function clearSpotifyParam(): void {
  const params = new URLSearchParams(window.location.search);
  if (!params.has("spotify")) return;
  params.delete("spotify");
  const rest = params.toString();
  navigate(`${window.location.pathname}${rest ? `?${rest}` : ""}`, { replace: true });
}
