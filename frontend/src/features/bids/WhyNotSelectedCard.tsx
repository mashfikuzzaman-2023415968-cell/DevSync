/**
 * "Why not selected" (spec §9.8, §13.5 #12): for the developer's own bid once a team was formed
 * without it: the main gap with a concrete hint, how the selected bid in the same role compared
 * (days and price only — never who), and the highest price at which this bid would have been
 * chosen. Nothing here names or identifies another bidder.
 */
import { Lightbulb } from "lucide-react";
import { ApiError } from "@/api/client";
import type { BidExplanationOut } from "@/api/types";
import { Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { ErrorState } from "@/components/ui/Feedback";
import { formatDays, formatMoney } from "@/lib/format";
import { useBidExplanation } from "@/features/formation/api";

const GAP_TITLE: Record<string, string> = {
  comp: "Competency made the biggest difference",
  team: "Teamwork made the biggest difference",
  time: "Delivery time made the biggest difference",
  cost: "Price made the biggest difference",
};
const REASON_TEXT: Record<string, string> = {
  NOT_SELECTED: "Your bid was eligible, and another combination of developers scored higher.",
  NOT_SHORTLISTED:
    "Your bid was eligible but didn’t make the shortlist for this role, so it wasn’t in the search.",
};

function concrete(e: BidExplanationOut): string | null {
  const c = e.compare;
  if (!c) return null;
  if (e.main_gap === "time") {
    return `The selected bid for this role needs ${formatDays(c.selected_days)}; yours needs ${formatDays(c.your_days)}.`;
  }
  if (e.main_gap === "cost") {
    return `The selected bid for this role is ${formatMoney(c.selected_price_paisa)}; yours is ${formatMoney(c.your_price_paisa)}.`;
  }
  return null;
}

export function WhyNotSelectedCard({ bidId }: { bidId: string }) {
  const q = useBidExplanation(bidId, true);
  if (q.isPending) {
    return (
      <Card className="p-5" aria-busy="true" aria-label="Loading why your bid was not selected">
        <Skeleton className="h-5 w-56" />
        <Skeleton className="mt-4 h-16 w-full" />
      </Card>
    );
  }
  if (q.isError) {
    const err = q.error;
    if (err instanceof ApiError && err.status === 404) {
      return (
        <Card>
          <CardHeader title="Why it wasn’t selected" />
          <p className="px-5 pb-5 pt-2 text-body-sm text-text-muted">
            The explanation is being prepared. Check back in a minute.
          </p>
        </Card>
      );
    }
    return (
      <Card>
        <ErrorState
          title="The explanation didn’t load"
          requestId={err instanceof ApiError ? err.requestId : null}
          onRetry={() => void q.refetch()}
        />
      </Card>
    );
  }
  const e = q.data;
  const detail = concrete(e);
  return (
    <Card>
      <CardHeader title="Why it wasn’t selected" />
      <div className="space-y-4 px-5 pb-5 pt-3 text-body-sm">
        {e.reasons.map((r) => (
          <p key={r} className="text-text">
            {REASON_TEXT[r] ??
              "Your bid didn’t meet this project’s requirements under the client’s settings."}
          </p>
        ))}
        {e.main_gap ? (
          <div className="rounded-lg bg-surface-2 p-4">
            <p className="flex items-center gap-2 font-semibold text-text">
              <Lightbulb className="size-4 text-primary" aria-hidden="true" />
              {GAP_TITLE[e.main_gap]}
            </p>
            {detail ? <p className="mt-1 text-text">{detail}</p> : null}
            {e.hint ? <p className="mt-1 text-text-muted">{e.hint}</p> : null}
          </div>
        ) : null}
        {e.price_counterfactual_paisa ? (
          <p className="text-text">
            At{" "}
            <span className="font-semibold tabular">
              {formatMoney(e.price_counterfactual_paisa)}
            </span>{" "}
            or less, you would have been selected.
          </p>
        ) : e.reasons.includes("NOT_SELECTED") && e.main_gap ? (
          <p className="text-text-muted">
            A lower price alone (down to half) wouldn’t have changed the result.
          </p>
        ) : null}
      </div>
    </Card>
  );
}
