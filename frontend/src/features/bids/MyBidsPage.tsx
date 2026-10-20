/**
 * My Bids (spec §13.5 #12): a developer's own bids with their status. The "why not selected"
 * explanations arrive in Phase 7; until then the status and a link to the project are shown.
 */
import { Link } from "react-router";
import { NodeArt } from "@/components/brand/NodeArt";
import { Button } from "@/components/ui/Button";
import { Badge, Card, Skeleton, type Tone } from "@/components/ui/Display";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { formatDays, formatMoney } from "@/lib/format";
import { useMyBids } from "./api";

const TONE: Record<string, Tone> = {
  ACTIVE: "info",
  WITHDRAWN: "neutral",
  INELIGIBLE: "warning",
  SELECTED: "success",
  NOT_SELECTED: "neutral",
  ACCEPTED: "success",
  DECLINED: "danger",
  EXPIRED: "neutral",
};

function label(status: string): string {
  return status.charAt(0) + status.slice(1).toLowerCase().replace(/_/g, " ");
}

export default function MyBidsPage() {
  const bids = useMyBids();

  return (
    <>
      <PageHeader title="My bids" description="Every sealed bid you've placed and its status." />
      {bids.isLoading ? (
        <Card>
          <Skeleton className="h-32 w-full" />
        </Card>
      ) : bids.isError ? (
        <Card>
          <ErrorState onRetry={() => void bids.refetch()} />
        </Card>
      ) : (bids.data ?? []).length === 0 ? (
        <Card>
          <EmptyState
            art={<NodeArt />}
            title="No bids yet"
            description="Find a project that fits your skills and place a sealed bid."
            action={
              <Button asChild variant="outline">
                <Link to="/dev/find">Find work</Link>
              </Button>
            }
          />
        </Card>
      ) : (
        <Card className="overflow-hidden p-0">
          <ul className="divide-y divide-border">
            {(bids.data ?? []).map((b) => (
              <li key={b.id} className="flex items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <Link
                    to={`/dev/projects/${b.project_id}`}
                    className="font-medium text-text hover:text-primary hover:underline"
                  >
                    View project
                  </Link>
                  <p className="mt-1 text-body-sm text-text-muted">
                    {formatMoney(b.price_paisa)} · {formatDays(b.days_needed)}
                  </p>
                </div>
                <Badge tone={TONE[b.status] ?? "neutral"}>{label(b.status)}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
