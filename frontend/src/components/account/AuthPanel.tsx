import { useState } from "react";
import type { FormEvent } from "react";
import { login, register } from "../../account/useAccount";
import { requestPasswordReset } from "../../services/api";
import { ErrorLine, NoticeLine, errorMessage } from "../Notice";
import { TextField } from "./TextField";

type Mode = "login" | "register" | "forgot";

const MIN_PASSWORD_LENGTH = 8;
const RESET_SENT_TEXT = "Falls es zu dieser Adresse einen Account gibt, ist ein Link unterwegs.";

const SUBMIT_LABEL: Readonly<Record<Mode, string>> = {
  login:    "Anmelden",
  register: "Account anlegen",
  forgot:   "Link anfordern",
};

/** Login, registration and "forgot password" — one form, switched by mode. */
export function AuthPanel() {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetSent, setResetSent] = useState(false);

  function switchMode(next: Mode): void {
    setMode(next);
    setError(null);
    setResetSent(false);
  }

  async function submit(e: FormEvent): Promise<void> {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "forgot") {
        await requestPasswordReset(email.trim());
        setResetSent(true);
      } else {
        await (mode === "login" ? login : register)({ email: email.trim(), password });
      }
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {mode !== "forgot" ? (
        <div className="seg w-full" role="group" aria-label="Anmelden oder registrieren">
          <button
            type="button"
            onClick={() => switchMode("login")}
            aria-pressed={mode === "login"}
            className={`seg-item ${mode === "login" ? "seg-item-on" : ""}`}
          >
            Anmelden
          </button>
          <button
            type="button"
            onClick={() => switchMode("register")}
            aria-pressed={mode === "register"}
            className={`seg-item ${mode === "register" ? "seg-item-on" : ""}`}
          >
            Registrieren
          </button>
        </div>
      ) : (
        <div className="space-y-1.5">
          <h3 className="text-sm font-semibold text-ink">Passwort vergessen</h3>
          <p className="text-xs text-ink-2 leading-relaxed">
            Gib deine E-Mail-Adresse ein. Wir schicken dir einen Link, mit dem du ein neues Passwort setzt.
          </p>
        </div>
      )}

      <form onSubmit={(e) => { void submit(e); }} className="space-y-4">
        <TextField
          label="E-Mail"
          type="email"
          name="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        {mode !== "forgot" && (
          <TextField
            label="Passwort"
            type="password"
            name="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            minLength={mode === "register" ? MIN_PASSWORD_LENGTH : undefined}
            hint={mode === "register" ? `Mindestens ${MIN_PASSWORD_LENGTH} Zeichen` : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        )}

        {error && <ErrorLine message={error} />}
        {resetSent && <NoticeLine notice={{ tone: "ok", text: RESET_SENT_TEXT }} />}

        <div className="flex items-center justify-between gap-4 pt-1">
          <button type="submit" disabled={busy} className="btn btn-primary h-8 px-3">
            {busy ? "Einen Moment…" : SUBMIT_LABEL[mode]}
          </button>
          {mode === "login" && (
            <button type="button" onClick={() => switchMode("forgot")} className="btn-quiet">
              Passwort vergessen?
            </button>
          )}
          {mode === "forgot" && (
            <button type="button" onClick={() => switchMode("login")} className="btn-quiet">
              Zurück zur Anmeldung
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
