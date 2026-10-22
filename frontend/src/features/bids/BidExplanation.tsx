/**
 * "Why eligible / not eligible" for one bid (spec §9.2, §13.10 "every algorithmic result gets
 * one sentence of why"): Algorithm 1's checks in the order the filter applies them, each with
 * what was required and what the bid had. The first failing check decides the verdict.
 */
import { CircleCheck, CircleX } from "lucide-react";
import { Link } from "react-router";
import type { ClientBid } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Badge, NewcomerBadge } from "@/components/ui/Display";
import { formatDate, formatMoney, formatPercent, formatScore } from "@/lib/format";
import { CHECK_LABEL, reasonText } from "./bidText";

export function Verdict({ bid }: { bid: ClientBid }) {
  if (bid.eligible && bid.shortlisted) return <Badge tone="success">Eligible</Badge>;
  if (bid.eligible) return <Badge tone="info">Eligible, not shortlisted</Badge>;
  return <Badge tone="warning">{reasonText(bid.reasons)}</Badge>;
}

function verdictSentence(bid: ClientBid): string {
  if (bid.newcomer_evidence && bid.eligible) {
    return `Eligible through the newcomer rule: ${bid.newcomer_evidence.skill} test ${formatPercent(bid.newcomer_evidence.score)}.`;
  }
  if (bid.eligible && bid.shortlisted) return "Meets every requirement of your project.";
  if (bid.eligible) {
    return "Meets every requirement, but other eligible bids for this slot rank higher.";
  }
  const first = bid.checks.find((c) => !c.ok);
  return first ? `Filtered out: ${first.detail}.` : `Filtered out: ${reasonText(bid.reasons)}.`;
}

export function BidExplanation({ bid }: { bid: ClientBid }) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Verdict bid={bid} />
          {bid.is_newcomer ? <NewcomerBadge /> : null}
        </div>
        <p className="text-body-sm text-text">{verdictSentence(bid)}</p>
        <Button asChild variant="outline">
          <Link to={`/d/${bid.developer_id}`}>View {bid.developer_name}’s profile</Link>
        </Button>
      </div>

      <section aria-labelledby="checks-title" className="space-y-3">
        <h3 id="checks-title" className="text-body font-semibold text-text">
          How the filter decided
        </h3>
        <ol className="space-y-2">
          {bid.checks.map((check) => (
            <li
              key={check.name}
              className="flex items-start gap-3 rounded-md border border-border bg-surface-2 px-3 py-2"
            >
              {check.ok ? (
                <CircleCheck className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
              ) : (
                <CircleX className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
              )}
              <span className="min-w-0">
                <span className="block text-body-sm font-medium text-text">
                  {CHECK_LABEL[check.name] ?? check.name}
                  <span className="sr-only">{check.ok ? ": met" : ": not met"}</span>
                </span>
                <span className="block text-body-sm text-text-muted">{check.detail}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-body-sm">
        <div>
          <dt className="text-text-muted">Price</dt>
          <dd className="tabular text-text">{formatMoney(bid.price_paisa)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Days needed</dt>
          <dd className="tabular text-text">{bid.days_needed}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Hours a week</dt>
          <dd className="tabular text-text">{bid.hours_per_week}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Submitted</dt>
          <dd className="text-text" data-volatile>
            {formatDate(bid.submitted_at)}
          </dd>
        </div>
        <div>
          <dt className="text-text-muted">Competency</dt>
          <dd className="tabular text-text">{formatScore(bid.competency)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Teamwork</dt>
          <dd className="tabular text-text">{formatScore(bid.teamwork)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Performance</dt>
          <dd className="tabular text-text">
            {bid.is_newcomer ? "New to DevSync" : formatScore(bid.performance)}
          </dd>
        </div>
      </dl>

      <section aria-labelledby="proposal-title" className="space-y-2">
        <h3 id="proposal-title" className="text-body font-semibold text-text">
          Proposal
        </h3>
        <p className="whitespace-pre-line text-body-sm text-text">
          {bid.proposal || "No proposal written."}
        </p>
        {bid.expected_contribution ? (
          <p className="text-body-sm text-text-muted">
            Expected contribution: {bid.expected_contribution}
          </p>
        ) : null}
        {bid.portfolio.length > 0 ? (
          <div>
            <p className="text-body-sm text-text-muted">Portfolio items</p>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-body-sm text-text">
              {bid.portfolio.map((item) => (
                <li key={item.id}>{item.title}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </div>
  );
}
