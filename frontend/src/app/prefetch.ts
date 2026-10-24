/**
 * Prefetch a main navigation destination's route chunk when the person points at or focuses its
 * link (spec §13.7 "prefetch on hover for main nav links"), so the page is already in memory
 * when they click.
 *
 * Only the pages that exist now are listed; destinations later phases build open a placeholder
 * that costs nothing to load. Each chunk is requested at most once per page load, and a failed
 * prefetch is ignored — the navigation itself loads it again and shows the real error.
 */

/** Route path → the module the router loads for it (same imports as app/router.tsx). */
const CHUNKS: Record<string, () => Promise<unknown>> = Object.assign(Object.create(null), {
  "/dev": () => import("@/features/home/DeveloperHome"),
  "/dev/find": () => import("@/features/marketplace/FindProjectsPage"),
  "/dev/bids": () => import("@/features/bids/MyBidsPage"),
  "/dev/challenges": () => import("@/features/challenges/ChallengesPage"),
  "/dev/profile": () => import("@/features/profile/ProfilePage"),
  "/client": () => import("@/features/home/ClientHome"),
  "/client/projects": () => import("@/features/projects/MyProjectsPage"),
  "/client/projects/new": () => import("@/features/projects/CreateProjectPage"),
  "/settings": () => import("@/features/account/SettingsPage"),
  // A null prototype, so "constructor" or "__proto__" from a crafted link is not a chunk.
}) as Record<string, () => Promise<unknown>>;

const started = new Set<string>();

/** True if this path's chunk can be prefetched (the page exists and isn't loaded yet). */
export function canPrefetch(path: string): boolean {
  return Object.hasOwn(CHUNKS, path) && !started.has(path);
}

/** Start loading the chunk behind `path`, at most once; unknown paths and failures are no-ops. */
export function prefetchRoute(path: string): void {
  const load = Object.hasOwn(CHUNKS, path) ? CHUNKS[path] : undefined;
  if (!load || started.has(path)) return;
  started.add(path);
  void load().catch(() => {
    // The chunk is loaded again (and any error shown) when the person actually navigates.
    started.delete(path);
  });
}

/** Props that make any link prefetch its chunk on hover, focus or touch. */
export function prefetchProps(path: string) {
  const start = () => {
    prefetchRoute(path);
  };
  return { onMouseEnter: start, onFocus: start, onTouchStart: start };
}

/** Testing only: forget which chunks were already requested. */
export function resetPrefetch(): void {
  started.clear();
}

/** Testing only: the paths this module knows how to prefetch. */
export function prefetchablePaths(): string[] {
  return Object.keys(CHUNKS);
}
