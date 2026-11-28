/**
 * Budget donut (spec §13.5 #29, §13.3; D151): released, committed (funded, not released) and
 * remaining, as a custom SVG ring with a legend (colour plus name and amount) and a "View as
 * table" alternative. Until Phase 10 brings escrow, released and committed are honestly zero, and
 * the donut says so.
 */
import { useState } from "react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { formatMoney } from "@/lib/format";

export interface BudgetParts {
  budget_paisa: number;
  released_paisa: number;
  committed_paisa: number;
  remaining_paisa: number;
}

const R = 42;
const C = 2 * Math.PI * R;

export function BudgetDonut({ budget }: { budget: BudgetParts }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const parts = [
    { label: "Released", paisa: budget.released_paisa, stroke: "stroke-chart-1", bg: "bg-chart-1" },
    {
      label: "Committed",
      paisa: budget.committed_paisa,
      stroke: "stroke-chart-2",
      bg: "bg-chart-2",
    },
    { label: "Remaining", paisa: budget.remaining_paisa, stroke: "stroke-border", bg: "bg-border" },
  ];
  const total = Math.max(1, budget.budget_paisa);
  let offset = 0;
  const arcs = parts.map((p) => {
    const len = (Math.max(0, p.paisa) / total) * C;
    const arc = { ...p, dash: `${String(len)} ${String(C - len)}`, offset: -offset };
    offset += len;
    return arc;
  });
  return (
    <figure className="space-y-3">
      <SegmentedControl<"chart" | "table">
        label="Budget view"
        size="sm"
        value={view}
        onChange={setView}
        segments={[
          { value: "chart", label: "Chart" },
          { value: "table", label: "View as table" },
        ]}
      />
      {view === "chart" ? (
        <div className="flex items-center gap-5">
          <svg
            viewBox="0 0 100 100"
            className="size-28 shrink-0 -rotate-90"
            role="img"
            aria-label={`Budget ${formatMoney(budget.budget_paisa)}: ${parts.map((p) => `${p.label.toLowerCase()} ${formatMoney(p.paisa)}`).join(", ")}`}
          >
            {arcs.map((a) => (
              <circle
                key={a.label}
                cx="50"
                cy="50"
                r={R}
                fill="none"
                strokeWidth="12"
                className={a.stroke}
                strokeDasharray={a.dash}
                strokeDashoffset={a.offset}
              />
            ))}
          </svg>
          <ul className="space-y-1 text-body-sm">
            {parts.map((p) => (
              <li key={p.label} className="flex items-center gap-2">
                <span className={`size-2.5 rounded-full ${p.bg}`} aria-hidden="true" />
                <span className="text-text-muted">{p.label}</span>
                <span className="tabular font-medium text-text">{formatMoney(p.paisa)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <table className="w-full text-body-sm">
          <tbody>
            {parts.map((p) => (
              <tr key={p.label} className="border-b border-border">
                <th scope="row" className="py-1.5 text-left font-normal text-text-muted">
                  {p.label}
                </th>
                <td className="tabular py-1.5 text-right text-text">{formatMoney(p.paisa)}</td>
              </tr>
            ))}
            <tr>
              <th scope="row" className="py-1.5 text-left font-medium">
                Budget
              </th>
              <td className="tabular py-1.5 text-right font-medium">
                {formatMoney(budget.budget_paisa)}
              </td>
            </tr>
          </tbody>
        </table>
      )}
      {budget.released_paisa === 0 && budget.committed_paisa === 0 ? (
        <figcaption className="text-caption text-text-muted">
          Nothing is funded or released yet: payments start with milestone funding.
        </figcaption>
      ) : null}
    </figure>
  );
}
