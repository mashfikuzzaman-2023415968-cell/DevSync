import { describe, expect, it } from "vitest";
import { orderingSystem, reputationSample } from "./sample";

/** Independent forward/backward pass so the homepage figures match the seed (rule 0.2.6). */
function cpm(ms: readonly { id: string; days: number; after: readonly string[] }[]) {
  const es: Record<string, number> = {};
  const ef: Record<string, number> = {};
  for (const m of ms) {
    es[m.id] = Math.max(0, ...m.after.map((a) => ef[a] ?? 0));
    ef[m.id] = (es[m.id] ?? 0) + m.days;
  }
  const finish = Math.max(...Object.values(ef));
  const lf: Record<string, number> = {};
  for (const m of [...ms].reverse()) {
    const succ = ms.filter((s) => s.after.includes(m.id));
    lf[m.id] = succ.length ? Math.min(...succ.map((s) => (lf[s.id] ?? 0) - s.days)) : finish;
  }
  return {
    finish,
    es,
    ef,
    slack: Object.fromEntries(ms.map((m) => [m.id, (lf[m.id] ?? 0) - (ef[m.id] ?? 0)])),
  };
}

describe("homepage sample project", () => {
  it("matches the CPM result stated in the seed (§18.2)", () => {
    const r = cpm(orderingSystem.milestones);
    expect(r.finish).toBe(orderingSystem.cpm.durationDays);
    for (const m of orderingSystem.milestones) {
      const s = orderingSystem.cpm.schedule[m.id];
      expect(r.es[m.id]).toBe(s?.es);
      expect(r.ef[m.id]).toBe(s?.ef);
      expect(r.slack[m.id]).toBe(s?.slack);
    }
    const critical = orderingSystem.milestones.filter((m) => r.slack[m.id] === 0).map((m) => m.id);
    expect(critical).toEqual(orderingSystem.cpm.critical);
  });
});

describe("homepage reputation sample", () => {
  it.each(reputationSample)(
    "$name: C and P follow Eq. 4 and Eq. 12 with default weights",
    (dev) => {
      const p = dev.params;
      const c = 0.7 * p.expertise + 0.3 * p.communication; // Eq. 4, f = 0.7
      const perf = 0.5 * p.quality + 0.25 * p.diversity + 0.25 * p.punctuality; // Eq. 12
      expect(Math.abs(c - dev.competency)).toBeLessThanOrEqual(0.005 + 1e-9); // table rounds to 2 decimals
      expect(Math.abs(perf - dev.performance)).toBeLessThanOrEqual(0.005 + 1e-9); // table rounds to 2 decimals
    },
  );
});
