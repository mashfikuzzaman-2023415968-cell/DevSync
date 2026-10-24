/**
 * Why the person was signed out (spec §13.4 "suspended → signed out with message"): the API
 * answers SESSION_EXPIRED or ACCOUNT_SUSPENDED (401) to the first request after a session
 * ended. The fetch wrapper notes it here and fires `SIGNED_OUT_EVENT`; the route guard sends
 * the person to /login with `reason=…`, and the login page explains what happened.
 */

export type SignedOutReason = "session_expired" | "account_suspended";

export const SIGNED_OUT_EVENT = "ds:signed-out";

const REASON_BY_CODE: Record<string, SignedOutReason> = {
  SESSION_EXPIRED: "session_expired",
  ACCOUNT_SUSPENDED: "account_suspended",
};

let pending: SignedOutReason | null = null;

/** The reason for an API error code, if it means "your session ended". */
export function reasonForCode(code: string): SignedOutReason | null {
  return REASON_BY_CODE[code] ?? null;
}

/** Remember why the session ended and tell the app (the guard then redirects). */
export function noteSignedOut(reason: SignedOutReason): void {
  // A suspension outranks an expiry noted by a parallel request.
  if (pending !== "account_suspended") pending = reason;
  window.dispatchEvent(new CustomEvent(SIGNED_OUT_EVENT, { detail: { reason } }));
}

/** The reason waiting to be shown, if any (the guard reads it when redirecting). */
export function signedOutReason(): SignedOutReason | null {
  return pending;
}

/** Forget it once the sign-in page has shown it (or the person signed in again). */
export function clearSignedOutReason(): void {
  pending = null;
}

/** Only these two values are accepted from the address bar; anything else shows nothing. */
export function parseReason(value: string | null): SignedOutReason | null {
  return value === "session_expired" || value === "account_suspended" ? value : null;
}

export const SIGNED_OUT_MESSAGES: Record<SignedOutReason, { title: string; body: string }> = {
  session_expired: {
    title: "Your session expired",
    body: "For your security we sign you out after a while without activity. Sign in again to pick up where you left off.",
  },
  account_suspended: {
    title: "This account is suspended",
    body: "You can’t sign in while it’s suspended. Contact support if you think this is a mistake.",
  },
};
