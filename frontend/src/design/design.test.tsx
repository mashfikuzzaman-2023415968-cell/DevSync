import { act, render, renderHook, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { durationMs, motionVariants } from "./motion";
import {
  applyStoredPreferences,
  MOTION_KEY,
  PreferencesProvider,
  THEME_KEY,
  usePreferences,
} from "./preferences";

const wrapper = ({ children }: { children: ReactNode }) => (
  <PreferencesProvider>{children}</PreferencesProvider>
);

describe("motion system (spec §13.2)", () => {
  it("matches the catalogue durations and mirrors them in CSS", () => {
    expect(durationMs).toMatchObject({ fast: 120, base: 180, slow: 280, page: 220 });
    const css = readFileSync(resolve(__dirname, "../index.css"), "utf8");
    for (const [name, ms] of Object.entries(durationMs)) {
      expect(css).toContain(`--dur-${name}: ${String(ms)}ms;`);
    }
  });

  it("reduces every variant to opacity-only fades of at most 120 ms", () => {
    const reduced = motionVariants(true);
    for (const [name, variant] of Object.entries(reduced)) {
      for (const state of Object.values(variant)) {
        const target = state as Record<string, unknown>;
        const moving = ["x", "y", "scale", "rotate", "filter"].filter((k) => {
          const v = target[k];
          return v !== undefined && v !== 0 && !(Array.isArray(v) && v.every((n) => n === 0));
        });
        expect(moving, `${name} moves under reduced motion`).toEqual([]);
        const t = target.transition as { duration?: number } | undefined;
        if (t?.duration !== undefined) expect(t.duration).toBeLessThanOrEqual(0.12);
      }
    }
  });

  it("uses transforms when motion is allowed", () => {
    const full = motionVariants(false);
    expect((full.card.hidden as { y: number }).y).toBe(8);
    expect((full.page.hidden as { y: number }).y).toBe(6);
    expect((full.reveal.hidden as { y: number }).y).toBe(16);
  });
});

describe("preferences", () => {
  afterEach(() => {
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
    delete document.documentElement.dataset.motion;
  });

  it("defaults to the system theme and full motion", () => {
    const { result } = renderHook(() => usePreferences(), { wrapper });
    expect(result.current.theme).toBe("system");
    expect(result.current.resolvedTheme).toBe("light");
    expect(result.current.reducedMotion).toBe(false);
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("persists an explicit theme and applies it to <html>", () => {
    const { result } = renderHook(() => usePreferences(), { wrapper });
    act(() => {
      result.current.setTheme("dark");
    });
    expect(result.current.resolvedTheme).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("dark");
    act(() => {
      result.current.setTheme("system");
    });
    expect(window.localStorage.getItem(THEME_KEY)).toBeNull();
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("reduces motion from the in-app setting and marks <html>", () => {
    const { result } = renderHook(() => usePreferences(), { wrapper });
    act(() => {
      result.current.setMotion("reduce");
    });
    expect(result.current.reducedMotion).toBe(true);
    expect(document.documentElement.dataset.motion).toBe("reduce");
    expect(window.localStorage.getItem(MOTION_KEY)).toBe("reduce");
  });

  it("applies stored choices before the first render and ignores junk", () => {
    window.localStorage.setItem(THEME_KEY, "dark");
    window.localStorage.setItem(MOTION_KEY, "reduce");
    applyStoredPreferences();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.dataset.motion).toBe("reduce");
    window.localStorage.setItem(THEME_KEY, "neon");
    applyStoredPreferences();
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("works without a provider (safe defaults)", () => {
    function Probe() {
      return <span>{usePreferences().resolvedTheme}</span>;
    }
    render(<Probe />);
    expect(screen.getByText("light")).toBeInTheDocument();
  });
});
