/**
 * Fairness dial (spec §9.5, §13.3): the minimum number of newcomers in the team, 0–2, as a
 * segmented control in the newcomer colour, with the cost of fairness from the last run beside
 * it. One sentence says what the setting does.
 */
import { Sprout } from "lucide-react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { formatPercent } from "@/lib/format";

export type Dial = "0" | "1" | "2";

export function FairnessDial({
  value,
  onChange,
  newcomersAvailable,
  cost,
}: {
  value: Dial;
  onChange: (value: Dial) => void;
  /** Shortlisted newcomers; the dial can't ask for more than exist. */
  newcomersAvailable: number;
  /** Cost of fairness from the last run (0–1), shown after a run. */
  cost?: number | null;
}) {
  const options = (["0", "1", "2"] as const).filter(
    (v) => Number(v) <= Math.max(0, newcomersAvailable),
  );
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-body-sm font-semibold text-text">
          <Sprout className="size-4 text-newcomer" aria-hidden="true" />
          Newcomers at least
        </span>
        {cost !== undefined && cost !== null ? (
          <span className="rounded-full bg-newcomer-bg px-2.5 py-0.5 text-caption font-medium tabular text-newcomer">
            Cost of fairness {formatPercent(cost)}
          </span>
        ) : null}
      </div>
      <SegmentedControl
        label="Newcomers at least"
        value={options.includes(value) ? value : "0"}
        onChange={onChange}
        segments={options.map((v) => ({ value: v, label: v }))}
        className="w-full [&>button]:flex-1"
      />
      <p className="text-caption text-text-muted">
        {newcomersAvailable === 0
          ? "No newcomer made the shortlist, so the team is chosen on merit alone."
          : "Gives developers new to DevSync a fair start. The cost shows how much team score it takes."}
      </p>
    </div>
  );
}
