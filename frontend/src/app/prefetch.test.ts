/** Nav prefetch (spec §13.7): one request per chunk, unknown paths ignored, drift caught. */
import { afterEach, describe, expect, it } from "vitest";
import { NAV, UPCOMING } from "./navigation";
import {
  canPrefetch,
  prefetchProps,
  prefetchRoute,
  prefetchablePaths,
  resetPrefetch,
} from "./prefetch";

afterEach(() => {
  resetPrefetch();
});

describe("prefetchRoute", () => {
  it("loads a known chunk once, however often it is hovered", async () => {
    expect(canPrefetch("/dev/profile")).toBe(true);
    prefetchRoute("/dev/profile");
    expect(canPrefetch("/dev/profile")).toBe(false);
    prefetchRoute("/dev/profile");
    prefetchRoute("/dev/profile");
    // The module really loads (it is the page the router opens for that path).
    const page = await import("@/features/profile/ProfilePage");
    expect(typeof page.default).toBe("function");
  });

  it("ignores paths it doesn't know, including crafted ones", () => {
    for (const path of [
      "/dev/reputation", // a later phase's placeholder
      "/nope",
      "",
      "//evil.example",
      "/dev/profile?x=1",
      "constructor",
      "__proto__",
      "toString",
    ]) {
      expect(canPrefetch(path)).toBe(false);
      expect(() => {
        prefetchRoute(path);
      }).not.toThrow();
    }
  });

  it("prefetches on hover, focus and touch", () => {
    const props = prefetchProps("/settings");
    expect(Object.keys(props).sort()).toEqual(["onFocus", "onMouseEnter", "onTouchStart"]);
    props.onFocus();
    expect(canPrefetch("/settings")).toBe(false);
  });

  it("every built navigation destination can be prefetched", () => {
    const upcoming = new Set(UPCOMING.map((i) => i.to));
    const built = [...NAV.DEVELOPER.sidebar, ...NAV.CLIENT.sidebar, ...NAV.DEVELOPER.tabs]
      .map((i) => i.to)
      .filter((to) => !upcoming.has(to));
    const known = new Set(prefetchablePaths());
    expect([...new Set(built)].filter((to) => !known.has(to))).toEqual([]);
  });

  it("never lists a destination that doesn't exist yet", () => {
    const upcoming = new Set(UPCOMING.map((i) => i.to));
    expect(prefetchablePaths().filter((p) => upcoming.has(p))).toEqual([]);
  });
});
