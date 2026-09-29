import { useSyncExternalStore } from "react";
import type { AnchorHTMLAttributes, MouseEvent } from "react";

// Minimal History-API router: the URL path is the page state, so reloads,
// deep links and the browser's back/forward buttons all work. nginx and the
// Vite dev server both fall back to index.html for unknown paths.

const NAVIGATE_EVENT = "app:navigate";

function subscribe(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  window.addEventListener(NAVIGATE_EVENT, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(NAVIGATE_EVENT, onChange);
  };
}

/** Current pathname without a trailing slash ("/" stays "/"). */
function getPath(): string {
  const p = window.location.pathname;
  return p.length > 1 ? p.replace(/\/+$/, "") : p;
}

export function usePath(): string {
  return useSyncExternalStore(subscribe, getPath);
}

export function navigate(to: string, { replace = false } = {}) {
  if (replace) {
    // Keep the entry's state: a replaced entry is still the one the user entered with.
    window.history.replaceState(window.history.state, "", to);
  } else {
    if (to === window.location.pathname + window.location.search) return;
    // Marks entries created inside the app, so goBack() knows history.back() stays in it.
    window.history.pushState({ inApp: true }, "", to);
  }
  window.dispatchEvent(new Event(NAVIGATE_EVENT));
}

/** Browser back if the previous entry belongs to the app, otherwise go to `fallback`. */
export function goBack(fallback: string) {
  if (window.history.state?.inApp) window.history.back();
  else navigate(fallback, { replace: true });
}

/** Plain click → client-side navigation; modifier/middle clicks keep the
 *  browser default (open in new tab etc.). */
export function isPlainLeftClick(e: MouseEvent): boolean {
  return e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;
}

interface LinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> {
  to: string;
}

export function Link({ to, onClick, ...rest }: LinkProps) {
  return (
    <a
      {...rest}
      href={to}
      onClick={(e) => {
        onClick?.(e);
        if (e.defaultPrevented || !isPlainLeftClick(e)) return;
        e.preventDefault();
        navigate(to);
      }}
    />
  );
}

export const songPath = (id: string) => `/songs/${encodeURIComponent(id)}`;
export const recommenderPath = (id: string) => `/recommender/${encodeURIComponent(id)}`;
