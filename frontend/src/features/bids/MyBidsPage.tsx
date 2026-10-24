/**
 * My Bids (spec §13.5 #12): a developer's own bids, newest first, with their status and — for a
 * bid filtered out when bidding closed — why, in plain words. Each bid opens its detail page
 * (`/dev/bids/:id`). Cursor-paged with "Load more" (§10.1). The "why not selected" explanations
 * arrive in Phase 7.
 */
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import { NodeArt } from "@/components/brand/NodeArt";
import { Button } from "@/components/ui/Button";
import { Badge, Card, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { formatDays, formatMoney } from "@/lib/format";
import { useMyBids } from "./api";
import { BID_STATUS_TONE, bidStatusLabel } from "./bidText";

export default function MyBidsPage() {
  const bids = useMyBids();
  const items = (bids.data?.pages ?? []).flatMap((page) => page.items);

  return (
    <>
      <PageHeader title="My bids" description="Every sealed bid you’ve placed and its status." />
      {bids.isPending ? (
        <Card className="p-5" aria-busy="true" aria-label="Loading your bids">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="mt-3 h-12 w-full" />
          <Skeleton className="mt-3 h-12 w-full" />
        </Card>
      ) : bids.isError ? (
        <Card>
          <ErrorState
            title="Your bids didn’t load"
            requestId={bids.error instanceof ApiError ? bids.error.requestId : null}
            onRetry={() => void bids.refetch()}
          />
        </Card>
      ) : items.length === 0 ? (
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
        <>
          <Card className="overflow-hidden p-0">
            <ul className="divide-y divide-border">
              {items.map((b) => (
                <li key={b.id} className="flex items-start justify-between gap-3 p-5">
                  <div className="min-w-0">
                    <Link
                      to={`/dev/bids/${b.id}`}
                      className="inline-flex min-h-11 max-w-full items-center font-medium text-text hover:text-primary hover:underline"
                    >
                      <span className="break-words">{b.project_title}</span>
                    </Link>
                    <p className="text-body-sm text-text-muted">
                      {b.slot_label}, {formatMoney(b.price_paisa)} for {formatDays(b.days_needed)}
                    </p>
                    {b.status === "INELIGIBLE" && (b.reasons ?? []).length > 0 ? (
                      <p className="mt-1 text-body-sm text-text">
                        {(b.reasons ?? []).map((r) => r.text).join(" ")}
                      </p>
                    ) : null}
                  </div>
                  <Badge tone={BID_STATUS_TONE[b.status] ?? "neutral"} className="shrink-0">
                    {bidStatusLabel(b.status)}
                  </Badge>
                </li>
              ))}
            </ul>
          </Card>
          {bids.hasNextPage ? (
            <div className="mt-4 flex justify-center">
              <Button
                variant="outline"
                loading={bids.isFetchingNextPage}
                onClick={() => void bids.fetchNextPage()}
              >
                Load more bids
              </Button>
            </div>
          ) : null}
        </>
      )}
    </>
  );
}
