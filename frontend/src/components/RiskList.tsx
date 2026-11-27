/**
 * Risks grouped Critical / Medium / Low (spec §13.5 #39; §9.11; D151). Each risk says what it is
 * in one line, why in one sentence, and offers the engine's suggested actions as links (re-plan on
 * the Timeline, discuss with the team, request removal or a replacement). Severity is an icon and
 * a word, never colour alone. A suggestion never acts by itself (§9.9).
 */
import { ShieldCheck } from "lucide-react";
import { Link } from "react-router";
import type { RiskItem } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Card, RiskChip } from "@/components/ui/Display";
import { EmptyState } from "@/components/ui/Feedback";
import { formatDateTime, formatRelative } from "@/lib/format";

const GROUPS = [
  { severity: "CRITICAL", label: "Critical" },
  { severity: "MEDIUM", label: "Medium" },
  { severity: "LOW", label: "Low" },
] as const;

/** Where an action leads in the workspace; `null` hides actions the viewer can't take. */
export type ActionTarget = (action: string, risk: RiskItem) => { to: string; label: string } | null;

export function RiskList({
  risks,
  target,
  compact = false,
}: {
  risks: RiskItem[];
  target: ActionTarget;
  /** The Overview's top-3: no group headings. */
  compact?: boolean;
}) {
  if (risks.length === 0) {
    return (
      <EmptyState
        icon={<ShieldCheck />}
        title="No open risks"
        description="Nothing in the plan, the pace or the team needs attention right now."
      />
    );
  }
  const items = (list: RiskItem[]) => (
    <ul className="space-y-3">
      {list.map((r) => (
        <li key={r.id}>
          <Card className="space-y-2 p-4">
            <div className="flex flex-wrap items-start gap-2">
              <RiskChip severity={r.severity} />
              <p className="min-w-0 flex-1 font-medium text-text">{r.title}</p>
            </div>
            {r.why ? <p className="text-body-sm text-text-muted">{r.why}</p> : null}
            <div className="flex flex-wrap items-center gap-2">
              {r.actions
                .map((a) => target(a, r))
                .filter((t): t is { to: string; label: string } => t !== null)
                .map((t) => (
                  <Button key={t.label} asChild size="sm" variant="outline">
                    <Link to={t.to}>{t.label}</Link>
                  </Button>
                ))}
              <span className="ml-auto text-caption text-text-muted">
                Opened{" "}
                <time dateTime={r.opened_at} title={formatDateTime(r.opened_at)} data-volatile>
                  {formatRelative(r.opened_at)}
                </time>
              </span>
            </div>
          </Card>
        </li>
      ))}
    </ul>
  );
  if (compact) return items(risks);
  return (
    <div className="space-y-6">
      {GROUPS.map((g) => {
        const list = risks.filter((r) => r.severity === g.severity);
        if (list.length === 0) return null;
        return (
          <section key={g.severity} aria-labelledby={`risks-${g.severity}`}>
            <h2 id={`risks-${g.severity}`} className="mb-3 text-body font-semibold">
              {g.label} <span className="tabular text-text-muted">({list.length})</span>
            </h2>
            {items(list)}
          </section>
        );
      })}
    </div>
  );
}
