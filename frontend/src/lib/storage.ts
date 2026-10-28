/** localStorage that never throws (private mode, blocked storage, SSR-like tests). Only
 * per-device conveniences live here: theme, motion setting, sidebar state. */
export function readPref(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writePref(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable: the preference lasts for this page view only.
  }
}

/** sessionStorage for the few things that must survive a reload of the same tab (role
 * assessment spec Decisions 13 and §7.4): a bid draft (non-sensitive text only) and the leaves
 * not yet acknowledged by the server. Only these key prefixes are allowed, nothing secret is
 * ever stored, and sign-out clears them (`clearSessionDrafts`). */
const SESSION_PREFIXES = ["devsync:bid-draft:", "devsync:pending-leaves:"] as const;

function allowedSessionKey(key: string): boolean {
  return SESSION_PREFIXES.some((prefix) => key.startsWith(prefix));
}

export function readSession<T>(key: string, fallback: T): T {
  if (!allowedSessionKey(key)) return fallback;
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeSession(key: string, value: unknown): void {
  if (!allowedSessionKey(key)) throw new Error(`sessionStorage key not allowed: ${key}`);
  try {
    if (value === null || value === undefined) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage unavailable: the value lasts for this page view only.
  }
}

/** Remove every allowed session key (sign-out, or a session that ended elsewhere). */
export function clearSessionDrafts(): void {
  try {
    const store = window.sessionStorage;
    for (let i = store.length - 1; i >= 0; i -= 1) {
      const key = store.key(i);
      if (key !== null && allowedSessionKey(key)) store.removeItem(key);
    }
  } catch {
    // Nothing to clear.
  }
}
