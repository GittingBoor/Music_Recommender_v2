import { useEffect, useState } from "react";
import { useAccount } from "../../account/useAccount";
import { clearSpotifyParam, readSpotifyNotice } from "../../account/spotifyNotice";
import type { Notice } from "../../account/spotifyNotice";
import { NoticeLine } from "../Notice";
import { AccountColumn } from "./AccountColumn";
import { AccountDetails } from "./AccountDetails";
import { AuthPanel } from "./AuthPanel";

/** /account — log in or register; once logged in, Spotify and logout. */
export function AccountPage() {
  const account = useAccount();
  const [notice] = useState<Notice | null>(readSpotifyNotice);

  useEffect(clearSpotifyParam, []);

  return (
    <AccountColumn title="Account">
      {notice && <NoticeLine notice={notice} />}
      {account === undefined && <p className="font-mono text-xs text-ink-3">Lade Account…</p>}
      {account === null && <AuthPanel />}
      {account && <AccountDetails account={account} />}
    </AccountColumn>
  );
}
