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
