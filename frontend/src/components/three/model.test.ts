import { describe, expect, it } from "vitest";
import {
  buildConstellation,
  IDLE_SNAP_MS,
  positionAt,
  rng,
  snapTarget,
  TEAM_TARGETS,
} from "./model";

describe("constellation model", () => {
  it("is deterministic for a seed", () => {
    expect(buildConstellation(48).nodes).toEqual(buildConstellation(48).nodes);
    expect(rng(1)()).toBe(rng(1)());
    expect(buildConstellation(48, 1).nodes).not.toEqual(buildConstellation(48, 2).nodes);
  });

  it("stays within the triangle and node budget (≤ 60 nodes)", () => {
    for (const n of [24, 48]) {
      const c = buildConstellation(n);
      expect(c.nodes).toHaveLength(n);
      expect(new Set(c.team).size).toBe(4);
      expect(c.links.length).toBeGreaterThanOrEqual(n);
      expect(c.links.every(([a, b]) => a < b && b < n)).toBe(true);
      for (const t of c.team) expect(c.accent.has(t)).toBe(false);
    }
  });

  it("moves the team to the front when snapped and back when released", () => {
    const c = buildConstellation(48);
    const close = (a: { x: number; y: number; z: number } | undefined, b: typeof a) => {
      for (const k of ["x", "y", "z"] as const) expect(a?.[k]).toBeCloseTo(b?.[k] ?? NaN, 9);
    };
    c.team.forEach((idx, slot) => {
      close(positionAt(c, idx, 1.3, 1), TEAM_TARGETS[slot]);
      close(positionAt(c, idx, 0, 0), c.nodes[idx]);
    });
    // Everyone else drifts outward, never into the team's space.
    const other = [...Array(48).keys()].find((i) => !c.team.includes(i)) ?? 0;
    expect(positionAt(c, other, 0, 1).z).toBeLessThan((c.nodes[other]?.z ?? 0) + 0.01);
  });

  it("snaps from scroll, or after 6 s idle until the visitor scrolls", () => {
    expect(snapTarget(0, 0, false)).toBe(0);
    expect(snapTarget(300, 0, true)).toBe(0.5);
    expect(snapTarget(900, 0, true)).toBe(1);
    expect(snapTarget(0, IDLE_SNAP_MS, false)).toBe(1);
    expect(snapTarget(0, IDLE_SNAP_MS, true)).toBe(0);
  });
});

describe("writePositions", () => {
  it("matches positionAt for every node at any angle and snap", async () => {
    const { writePositions } = await import("./model");
    const c = buildConstellation(48);
    const out = new Float32Array(48 * 3);
    for (const [angle, snap] of [
      [0, 0],
      [1.1, 0.4],
      [4.2, 1],
    ] as const) {
      writePositions(c, angle, snap, out);
      c.nodes.forEach((_, i) => {
        const p = positionAt(c, i, angle, snap);
        expect(out[i * 3]).toBeCloseTo(p.x, 4);
        expect(out[i * 3 + 1]).toBeCloseTo(p.y, 4);
        expect(out[i * 3 + 2]).toBeCloseTo(p.z, 4);
      });
    }
  });
});
