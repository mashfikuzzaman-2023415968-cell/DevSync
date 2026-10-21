/**
 * Client Bids table (spec §13.5 #23, §13.9): the project's client sees every bid with the
 * developer's competency/performance and the Algorithm 1 eligibility verdict + reason, slot
 * coverage, and — when there aren't enough eligible bids — the too-few-bids banner with its
 * actions (§9.19). Reputation shown ×100; a "seeded" marker appears outside production.
 */
import { useParams } from "react-router";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import type { ClientBid } from "@/api/types";
import { Badge, Card, NewcomerBadge, Skeleton } from "@/components/ui/Display";
import { Button } from "@/components/ui/Button";
import { Alert, EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { formatDays, formatMoney, formatScore } from "@/lib/format";
import { useClientBids } from "./api";

const REASON_TEXT: Record<string, string> = {
  LOW_PERFORMANCE: "Performance below minimum",
  LOW_COMPETENCY: "Competency below minimum",
  TOO_SLOW: "Too slow for the deadline",
  OVER_BUDGET: "Over budget",
  NO_SKILL_EVIDENCE: "No passing skill test",
  SKILL_MISMATCH: "Missing the slot's skill",
  UNAVAILABLE: "Not enough free hours",
  SUSPENDED: "Account not active",
  SELF_DEALING: "Conflict of interest",
  NOT_SHORTLISTED: "Not in the top shortlist",
};

export default function ClientBidsPage() {
  const { id = "" } = useParams();
  const bids = useClientBids(id);

  if (bids.isLoading) {
    return (
      <>
        <PageHeader title="Bids" />
        <Card>
          <Skeleton className="h-48 w-full" />
        </Card>
      </>
    );
  }
  if (bids.isError || !bids.data) {
    const err = bids.error;
    return (
      <>
        <PageHeader title="Bids" />
        <Card>
          <ErrorState
            requestId={err instanceof ApiError ? err.requestId : null}
            onRetry={() => void bids.refetch()}
          />
        </Card>
      </>
    );
  }

  const data = bids.data;
  const coverageText = data.coverage
    .map((c) => `${c.slot_label} ${c.eligible}/${c.needed}`)
    .join(" · ");

  return (
    <>
      <PageHeader title="Bids" description={coverageText || "Bids on your project."} />

      {data.too_few ? (
        <Alert tone="warning" title="Not enough eligible bids yet" className="mb-6">
          Some slots don’t have enough eligible bids. You can:
          <div className="mt-3 flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to={`/client/projects/${id}/plan`}>Extend or adjust the project</Link>
            </Button>
          </div>
          {data.relaxations.length > 0 ? (
            <p className="mt-2 text-caption text-text-muted">
              Standards were relaxed to{" "}
              {data.relaxations
                .map((r) => `P ${Math.round(r.p0 * 100)} / C ${Math.round(r.c0 * 100)}`)
                .join(", ")}{" "}
              to find candidates.
            </p>
          ) : null}
        </Alert>
      ) : null}

      {data.bids.length === 0 ? (
        <Card>
          <EmptyState
            title="No bids yet"
            description="Bids will appear here as developers apply."
          />
        </Card>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-body-sm">
            <caption className="sr-only">Bids with developer, reputation and eligibility.</caption>
            <thead>
              <tr className="border-b border-border text-left text-text-muted">
                <th scope="col" className="py-2 pr-3 font-medium">
                  Developer
                </th>
                <th scope="col" className="py-2 px-3 font-medium">
                  Role
                </th>
                <th scope="col" className="py-2 px-3 text-right font-medium tabular">
                  Price
                </th>
                <th scope="col" className="py-2 px-3 text-right font-medium tabular">
                  Days
                </th>
                <th scope="col" className="py-2 px-3 text-right font-medium tabular">
                  C
                </th>
                <th scope="col" className="py-2 px-3 text-right font-medium tabular">
                  P
                </th>
                <th scope="col" className="py-2 pl-3 font-medium">
                  Eligibility
                </th>
              </tr>
            </thead>
            <tbody>
              {data.bids.map((b) => (
                <BidRow key={b.id} bid={b} />
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}

function BidRow({ bid }: { bid: ClientBid }) {
  return (
    <tr className="border-b border-border/60 last:border-0">
      <th scope="row" className="py-2 pr-3 font-normal text-text">
        <span className="flex items-center gap-2">
          {bid.developer_name}
          {bid.is_newcomer ? <NewcomerBadge /> : null}
          {bid.seeded ? <span className="text-caption text-text-subtle">seeded</span> : null}
        </span>
      </th>
      <td className="py-2 px-3 text-text-muted">{bid.slot_label}</td>
      <td className="py-2 px-3 text-right tabular">{formatMoney(bid.price_paisa)}</td>
      <td className="py-2 px-3 text-right tabular">{formatDays(bid.days_needed)}</td>
      <td className="py-2 px-3 text-right tabular">{formatScore(bid.competency)}</td>
      <td className="py-2 px-3 text-right tabular">{formatScore(bid.performance)}</td>
      <td className="py-2 pl-3">
        {bid.eligible ? (
          <Badge tone="success">Eligible</Badge>
        ) : (
          <Badge tone="warning">
            {bid.reasons.map((r) => REASON_TEXT[r] ?? r).join(", ") || "Ineligible"}
          </Badge>
        )}
      </td>
    </tr>
  );
}
