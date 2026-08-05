// Internal-pilot access gate (docs/deployment.md's Render section). Backs
// PilotAccessGate.tsx + usePilotAccess.ts. THIS IS NOT REAL AUTHENTICATION --
// it proves "has the shared pilot key" (SEMA_API_KEY on the server), never a
// per-user identity or tenant authorization. Real login is auth_login_prompt.md
// Parts A+B; this exists only to keep an unlisted Render pilot URL from being
// a bare, unauthenticated admin panel in the meantime.
//
// The key lives in sessionStorage ONLY (never localStorage): closing the tab
// forgets it, matching "temporary" -- and it's read fresh by every request
// rather than kept in React state, so a hard reload never re-prompts.

const STORAGE_KEY = "sema_pilot_access_key";

export function getAccessKey(): string | null {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    // Storage disabled (private-mode edge cases) -- treat as "no key",
    // which just means every request goes unauthenticated and 401s, same
    // as a fresh tab that hasn't entered one yet.
    return null;
  }
}

export function setAccessKey(key: string): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, key);
  } catch {
    // See getAccessKey -- nothing to recover here, the next request will
    // simply 401 and the gate reappears.
  }
}

export function clearAccessKey(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // See getAccessKey.
  }
}

/** Fired on `window` whenever a protected request comes back 401 -- lib/api.ts's
 * fetch helpers have no component tree to lift state into, so a DOM event is
 * the simplest way to tell usePilotAccess (wherever it's mounted) "the stored
 * key just stopped working, show the gate again." Covers the case where an
 * admin rotates/expires the key while a tab is already open (no page reload
 * happens on its own to re-trigger the initial probe). */
export const ACCESS_REVOKED_EVENT = "sema:pilot-access-revoked";

export function revokeAccess(): void {
  clearAccessKey();
  window.dispatchEvent(new Event(ACCESS_REVOKED_EVENT));
}

/** `{ "X-API-Key": ... }` merged over `extra`, or just `extra` when no key is
 * stored -- so every fetch call site in lib/api.ts stays a one-line change.
 * Sending no header (rather than an empty one) matters: it's what makes
 * local dev with an empty SEMA_API_KEY behave exactly as before this gate
 * existed. */
export function withAccessKeyHeader(extra?: Record<string, string>): Record<string, string> {
  const key = getAccessKey();
  return key ? { ...extra, "X-API-Key": key } : { ...extra };
}
