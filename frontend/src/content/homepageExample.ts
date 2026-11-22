/**
 * The homepage's fairness figures (rule 0.2.6, DECISIONS D21, D113): a real DevSync run on the
 * seeded “Online ordering system” at each dial setting, written by
 * `backend/scripts/formation_check.py --homepage` and checked fresh by the Phase 7 gate. Nothing
 * here is typed in by hand.
 */
import example from "./homepage-example.json";

export type DialSetting = "0" | "1" | "2";

export interface DialResult {
  newcomers: number;
  cost_of_fairness: number;
  team_size: number;
  optimal: boolean | null;
}

export const homepageExample = example as {
  source: string;
  project: string;
  dial: Record<DialSetting, DialResult>;
};

/** "2.1%" — the cost of fairness at a dial setting, one decimal at most. */
export function fairnessCost(setting: DialSetting): string {
  const cost = homepageExample.dial[setting].cost_of_fairness;
  return `${(cost * 100).toFixed(1).replace(/\.0$/, "")}%`;
}
