/**
 * Mirror of the server's open-redirect validator (backend/app/core/redirects.py):
 * only same-site app paths that match a known route are followed; everything else
 * falls back to the role's home page.
 */
// Known route shapes, matched segment by segment (no backtracking-prone patterns).
const SEGMENT = /^[A-Za-z0-9._~-]+$/;
const EXACT = new Set(["/", "/projects", "/verify", "/settings", "/notifications"]);
const ONE_MORE = new Set(["p", "d"]); // /p/:id, /d/:id
const ANY_MORE = new Set(["client", "dev", "admin"]); // /client, /client/…
const AT_LEAST_ONE_MORE = new Set(["w"]); // /w/:projectId/…

function matchesKnownRoute(path: string): boolean {
  if (EXACT.has(path)) return true;
  const [head = "", ...rest] = path.slice(1).split("/");
  if (!rest.every((seg) => SEGMENT.test(seg))) return false;
  if (ONE_MORE.has(head)) return rest.length === 1;
  if (ANY_MORE.has(head)) return true;
  if (AT_LEAST_ONE_MORE.has(head)) return rest.length >= 1;
  return false;
}

const ROLE_HOME: Record<string, string> = {
  CLIENT: "/client",
  DEVELOPER: "/dev",
  ADMIN: "/admin",
};

// eslint-disable-next-line no-control-regex -- control characters are exactly what we reject
const FORBIDDEN = /[\u0000- \u007f\\]/;

export function isSafePath(target: string | null | undefined): target is string {
  if (!target || target.length > 512) return false;
  let decoded: string;
  try {
    decoded = decodeURIComponent(target);
  } catch {
    return false;
  }
  for (const candidate of [target, decoded]) {
    if (!candidate.startsWith("/") || candidate.startsWith("//")) return false;
    if (FORBIDDEN.test(candidate)) return false;
  }
  const path = target.split(/[?#]/, 1)[0] ?? "";
  return matchesKnownRoute(path);
}

export function roleHome(role?: string | null, status?: string | null): string {
  if (status === "PENDING") return "/verify";
  return (role && ROLE_HOME[role]) ?? "/";
}

export function safeRedirect(
  target: string | null | undefined,
  role?: string | null,
  status?: string | null,
): string {
  if (status === "PENDING") return "/verify";
  return isSafePath(target) ? target : roleHome(role, status);
}
