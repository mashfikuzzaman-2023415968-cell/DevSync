/**
 * Team card (spec §13.3, §9.7): one member of the recommended team: who, which role, price and
 * days, competency and teamwork, and how much each fitness term contributed (bars on a shared
 * scale, numbers beside them, so colour is never the only signal; speed and cost are subtracted
 * in Eq. 17, so their numbers carry a minus sign, and the bars keep their term colour — rose is
 * for risks). Newcomers get the amber ring
 * and badge.
 */
import type { TeamMember } from "@/api/types";
import { Avatar, Card, NewcomerBadge } from "@/components/ui/Display";
import { cn } from "@/lib/cn";
import { formatDays, formatMoney, formatScore } from "@/lib/format";

export const TERM_LABEL = {
  comp: "Competency",
  team: "Teamwork",
  time: "Speed",
  cost: "Cost",
} as const;
type Term = keyof typeof TERM_LABEL;
const TERMS: readonly Term[] = ["comp", "team", "time", "cost"];
const BAR = { comp: "bg-chart-1", team: "bg-chart-2", time: "bg-chart-3", cost: "bg-chart-4" };

export function TeamCard({ member, scale }: { member: TeamMember; scale: number }) {
  const c = member.contribution;
  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex items-start gap-3">
        <Avatar name={member.developer_name} newcomer={member.is_newcomer} />
        <div className="min-w-0">
          <p className="truncate text-body font-semibold text-text">{member.developer_name}</p>
          <p className="text-body-sm text-text-muted">{member.slot_label}</p>
          {member.is_newcomer ? <NewcomerBadge className="mt-1.5" /> : null}
        </div>
      </div>
      <dl className="grid grid-cols-2 gap-3 text-body-sm">
        <div>
          <dt className="text-text-muted">Price</dt>
          <dd className="font-semibold tabular text-text">{formatMoney(member.price_paisa)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Time</dt>
          <dd className="font-semibold tabular text-text">{formatDays(member.days_needed)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Competency</dt>
          <dd className="font-semibold tabular text-text">{formatScore(member.competency)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Teamwork</dt>
          <dd className="font-semibold tabular text-text">{formatScore(member.teamwork)}</dd>
        </div>
      </dl>
      <div>
        <p className="text-caption font-medium text-text-muted">Contribution to the team score</p>
        <ul className="mt-2 space-y-1.5">
          {TERMS.map((t) => {
            const v = c[t];
            const share = scale > 0 ? Math.max(0, Math.min(1, Math.abs(v) / scale)) : 0;
            return (
              <li key={t} className="grid grid-cols-[5.5rem_minmax(0,1fr)_3rem] items-center gap-2">
                <span className="text-caption text-text-muted">{TERM_LABEL[t]}</span>
                <span
                  className="h-1.5 overflow-hidden rounded-full bg-surface-2"
                  aria-hidden="true"
                >
                  <span
                    className={cn("block h-full origin-left rounded-full", BAR[t])}
                    style={{ transform: `scaleX(${share.toFixed(3)})` }}
                  />
                </span>
                <span className="text-right text-caption tabular text-text">
                  {v < 0 ? "−" : ""}
                  {Math.abs(v).toFixed(2)}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </Card>
  );
}
