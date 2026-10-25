import { useSyncExternalStore } from "react";
import { fetchAccount, loginAccount, logoutAccount, registerAccount } from "../services/api";
import type { Account, Credentials } from "../services/api";

// One shared account state for the header and every page, loaded lazily on
// the first subscription. undefined = still loading, null = logged out.

type AccountState = Account | null | undefined;

const listeners = new Set<() => void>();
let state: AccountState = undefined;
let initialLoad: Promise<void> | null = null;

function setState(next: AccountState): void {
  state = next;
  for (const listener of listeners) listener();
}

/** Reloads the account from the server (e.g. after a cookie was set elsewhere). */
export async function refreshAccount(): Promise<void> {
  setState(await fetchAccount());
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  initialLoad ??= refreshAccount().catch((err: unknown) => {
    // Unreachable backend: show the logged-out state instead of loading forever.
    console.error("Account could not be loaded:", err);
    setState(null);
  });
  return () => {
    listeners.delete(onChange);
  };
}

const getState = (): AccountState => state;

export function useAccount(): AccountState {
  return useSyncExternalStore(subscribe, getState);
}

export async function login(credentials: Credentials): Promise<void> {
  setState(await loginAccount(credentials));
}

export async function register(credentials: Credentials): Promise<void> {
  setState(await registerAccount(credentials));
}

export async function logout(): Promise<void> {
  await logoutAccount();
  setState(null);
}
