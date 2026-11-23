/**
 * Priority sliders (spec §13.3, §9.2): the four fitness weights C1–C4 as percentages that always
 * total 100 %. Moving one slider spreads the difference over the other three in proportion to
 * their size (largest remainder, so the total stays exactly 100). The server normalises again,
 * so what is shown is what is used.
 */
import { Slider } from "@/components/ui/Slider";

export type WeightKey = "competency" | "teamwork" | "time" | "cost";
export type Weights = Record<WeightKey, number>;

export const WEIGHT_KEYS: readonly WeightKey[] = ["competency", "teamwork", "time", "cost"];
const LABEL: Record<WeightKey, string> = {
  competency: "Competency",
  teamwork: "Teamwork",
  time: "Speed",
  cost: "Cost",
};
const HINT: Record<WeightKey, string> = {
  competency: "How skilled each developer is.",
  teamwork: "How well they work with others.",
  time: "How quickly they can finish.",
  cost: "How much of the budget they need.",
};

/** Whole percentages from shares that sum to 1 (largest remainder, total exactly 100). */
export function toPercents(shares: Weights): Weights {
  const total = WEIGHT_KEYS.reduce((t, k) => t + Math.max(0, shares[k]), 0) || 1;
  const raw = WEIGHT_KEYS.map((k) => (Math.max(0, shares[k]) / total) * 100);
  const floors = raw.map(Math.floor);
  let left = 100 - floors.reduce((a, b) => a + b, 0);
  const order = raw
    .map((r, i) => ({ i, frac: r - Math.floor(r) }))
    .sort((a, b) => b.frac - a.frac || a.i - b.i);
  for (const { i } of order) {
    if (left <= 0) break;
    floors[i] = (floors[i] ?? 0) + 1;
    left -= 1;
  }
  const [competency = 0, teamwork = 0, time = 0, cost = 0] = floors;
  return { competency, teamwork, time, cost };
}

/** Set one weight to `value` %, spreading the change over the others (total stays 100). */
export function rebalance(current: Weights, key: WeightKey, value: number): Weights {
  const v = Math.min(100, Math.max(0, Math.round(value)));
  const others = WEIGHT_KEYS.filter((k) => k !== key);
  const rest = others.reduce((t, k) => t + current[k], 0);
  const shares: Weights = { ...current, [key]: v };
  for (const k of others) {
    shares[k] = rest > 0 ? (current[k] / rest) * (100 - v) : (100 - v) / others.length;
  }
  return toPercents(shares);
}

export function PrioritySliders({
  value,
  onChange,
  disabled = false,
}: {
  value: Weights;
  onChange: (next: Weights) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset className="space-y-4" disabled={disabled}>
      <legend className="text-body-sm font-semibold text-text">Priorities</legend>
      <p className="-mt-2 text-caption text-text-muted">Always add up to 100%.</p>
      {WEIGHT_KEYS.map((k) => (
        <div key={k}>
          <Slider
            label={LABEL[k]}
            value={value[k]}
            onChange={(v) => {
              onChange(rebalance(value, k, v));
            }}
            format={(v) => `${String(v)}%`}
            disabled={disabled}
          />
          <p className="mt-1 text-caption text-text-muted">{HINT[k]}</p>
        </div>
      ))}
    </fieldset>
  );
}
