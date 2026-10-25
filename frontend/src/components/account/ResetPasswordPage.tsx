import { useState } from "react";
import type { FormEvent } from "react";
import { refreshAccount } from "../../account/useAccount";
import { resetPassword } from "../../services/api";
import { Link, navigate } from "../../router";
import { ErrorLine, errorMessage } from "../Notice";
import { AccountColumn } from "./AccountColumn";
import { TextField } from "./TextField";

const MIN_PASSWORD_LENGTH = 8;

function validationError(password: string, repeat: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) return `Das Passwort braucht mindestens ${MIN_PASSWORD_LENGTH} Zeichen.`;
  if (password !== repeat) return "Die beiden Passwörter stimmen nicht überein.";
  return null;
}

/** /reset-password/:token — set a new password; success logs the account in. */
export function ResetPasswordPage({ token }: { readonly token: string }) {
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent): Promise<void> {
    e.preventDefault();
    const invalid = validationError(password, repeat);
    setError(invalid);
    if (invalid) return;
    setBusy(true);
    try {
      await resetPassword(token, password);
      await refreshAccount();
      navigate("/account", { replace: true });
    } catch (err: unknown) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <AccountColumn title="Neues Passwort">
      <form onSubmit={(e) => { void submit(e); }} className="space-y-4" noValidate>
        <TextField
          label="Neues Passwort"
          type="password"
          name="new-password"
          autoComplete="new-password"
          hint={`Mindestens ${MIN_PASSWORD_LENGTH} Zeichen`}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          label="Passwort wiederholen"
          type="password"
          name="repeat-password"
          autoComplete="new-password"
          value={repeat}
          onChange={(e) => setRepeat(e.target.value)}
        />
        {error && <ErrorLine message={error} />}
        <div className="flex items-center justify-between gap-4 pt-1">
          <button type="submit" disabled={busy} className="btn btn-primary h-8 px-3">
            {busy ? "Einen Moment…" : "Passwort speichern"}
          </button>
          <Link to="/account" className="btn-quiet">Neuen Link anfordern</Link>
        </div>
      </form>
    </AccountColumn>
  );
}
