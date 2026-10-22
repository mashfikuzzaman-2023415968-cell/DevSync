/**
 * Client Bids (spec §13.5 #23, §13.9): every bid on the client's project with the developer's
 * reputation and the Algorithm 1 verdict. Places covered per slot, the cheapest eligible team
 * against the budget, any automatic relaxation of the minimums, filters by slot and
 * eligibility, and for each bid a "How the filter decided" panel with every check and its
 * values. When eligible bids fall short, "Fix the shortfall" opens the five §9.19 actions.
 * Phones get a card list instead of the table. Reputation is shown ×100; "seeded" marks the
 * Phase 5 fixture values outside production.
 */
import { useMemo, useState } from "react";
import { useParams } from "react-router";
import { ApiError } from "@/api/client";
import type { ClientBid, ClientBids } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Card, NewcomerBadge, Skeleton } from "@/components/ui/Display";
import { Alert, EmptyState, ErrorState, PageHeader, Progress } from "@/components/ui/Feedback";
import { Sheet } from "@/components/ui/Overlay";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { formatDateTime, formatMoney, formatRelative, formatScore } from "@/lib/format";
import { useProject } from "@/features/projects/api";
import { useClientBids } from "./api";
import { BidExplanation, Verdict } from "./BidExplanation";
import { TooFewDialog } from "./TooFewDialog";

type EligibilityFilter = "all" | "eligible" | "ineligible";
const ALL_SLOTS = "all";

export default function ClientBidsPage() {
  const { id = "" } = useParams();
  const bids = useClientBids(id);
  const project = useProject(id);

  if (bids.isLoading) {
    return (
      <>
        <PageHeader title="Bids" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
        <Card className="mt-6">
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
  return (
    <BidsView
      view={bids.data}
      title={project.data?.title}
      project={project.data}
      onChanged={() => {
        void bids.refetch();
        void project.refetch();
      }}
    />
  );
}

function BidsView({
  view,
  title,
  project,
  onChanged,
}: {
  view: ClientBids;
  title: string | undefined;
  project: ReturnType<typeof useProject>["data"];
  onChanged: () => void;
}) {
  const [slot, setSlot] = useState(ALL_SLOTS);
  const [eligibility, setEligibility] = useState<EligibilityFilter>("all");
  const [openBid, setOpenBid] = useState<ClientBid | null>(null);
  const [fixOpen, setFixOpen] = useState(false);

  const shown = useMemo(
    () =>
      view.bids.filter(
        (b) =>
          (slot === ALL_SLOTS || b.slot_id === slot) &&
          (eligibility === "all" || (eligibility === "eligible") === b.eligible),
      ),
    [view.bids, slot, eligibility],
  );
  const eligibleCount = view.bids.filter((b) => b.eligible).length;
  // The §9.19 actions apply while the project is still BIDDING (before or after its deadline).
  const fixable = view.too_few && project?.status === "BIDDING" ? project : null;

  return (
    <>
      <PageHeader
        title="Bids"
        description={title ? `On “${title}”` : "Bids on your project."}
        action={
          fixable ? (
            <Button
              onClick={() => {
                setFixOpen(true);
              }}
            >
              Fix the shortfall
            </Button>
          ) : null
        }
      />

      {view.too_few ? (
        <Alert tone="warning" title="Not enough eligible bids yet" className="mb-6">
          {shortfallText(view)} You can extend bidding, lower the minimum standards, raise the
          budget, reduce the team, or cancel.
        </Alert>
      ) : null}
      {view.relaxations.length > 0 ? (
        <Alert tone="info" title="Minimums relaxed to find candidates" className="mb-6">
          {relaxationText(view)}
        </Alert>
      ) : null}

      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="text-body font-semibold text-text">Places covered</h2>
          <ul className="mt-3 space-y-3">
            {view.coverage.map((c) => (
              <li key={c.slot_id}>
                <Progress
                  label={`${c.slot_label || "Slot"}: ${String(Math.min(c.eligible, c.needed))} of ${String(c.needed)} ${c.needed === 1 ? "place" : "places"} covered`}
                  value={Math.min(c.eligible, c.needed)}
                  max={c.needed}
                  tone={c.eligible >= c.needed ? "success" : "warning"}
                />
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <h2 className="text-body font-semibold text-text">Cheapest eligible team</h2>
          {view.team_cost.complete ? (
            <p className="mt-3 text-h3 font-semibold tabular text-text">
              {formatMoney(view.team_cost.total_paisa)}
            </p>
          ) : (
            <p className="mt-3 text-body text-text">Not every place can be filled yet.</p>
          )}
          <p className="mt-1 text-body-sm text-text-muted">
            Of {formatMoney(view.team_cost.budget_after_fee_paisa)} budget after the platform fee.
            Team formation weighs quality, speed and cost, so the final team may cost more.
          </p>
          <p className="mt-3 text-body-sm text-text-muted">
            {view.bidding.deadline
              ? `Bidding ${view.bidding.closed ? "closed" : "closes"} ${formatRelative(view.bidding.deadline)}.`
              : "Bidding is open."}
          </p>
        </Card>
      </div>

      {view.bids.length === 0 ? (
        <Card>
          <EmptyState
            title="No bids yet"
            description="Bids appear here as developers apply. Sealed: they never see each other’s bids."
          />
        </Card>
      ) : (
        <Card>
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <span className="w-48">
                <Select
                  aria-label="Filter by slot"
                  value={slot}
                  onChange={setSlot}
                  options={[
                    { value: ALL_SLOTS, label: "All slots" },
                    ...view.coverage.map((c) => ({
                      value: c.slot_id,
                      label: c.slot_label || "Slot",
                    })),
                  ]}
                />
              </span>
              <SegmentedControl
                label="Filter by eligibility"
                value={eligibility}
                onChange={setEligibility}
                segments={[
                  { value: "all", label: "All" },
                  { value: "eligible", label: "Eligible" },
                  { value: "ineligible", label: "Not eligible" },
                ]}
              />
            </div>
            <p className="text-body-sm text-text-muted tabular">
              {view.bids.length} {view.bids.length === 1 ? "bid" : "bids"}, {eligibleCount} eligible
            </p>
          </div>

          {shown.length === 0 ? (
            <EmptyState
              title="No bids match these filters"
              description="Choose another slot or show all bids."
            />
          ) : (
            <>
              <BidTable
                bids={shown}
                onOpen={(b) => {
                  setOpenBid(b);
                }}
              />
              <BidCards
                bids={shown}
                onOpen={(b) => {
                  setOpenBid(b);
                }}
              />
            </>
          )}
          <p
            className="mt-4 text-caption text-text-muted"
            title={formatDateTime(view.evaluated_at)}
          >
            Eligibility checked {formatRelative(view.evaluated_at)} with minimum performance{" "}
            {formatScore(view.thresholds.used_p0)} and competency{" "}
            {formatScore(view.thresholds.used_c0)}.
          </p>
        </Card>
      )}

      <Sheet
        open={openBid !== null}
        onOpenChange={(o) => {
          if (!o) setOpenBid(null);
        }}
        title={openBid ? openBid.developer_name : "Bid"}
        description={openBid ? `${openBid.slot_label || "Slot"} bid` : undefined}
      >
        {openBid ? <BidExplanation bid={openBid} /> : null}
      </Sheet>

      {fixable ? (
        <TooFewDialog
          open={fixOpen}
          onOpenChange={setFixOpen}
          project={fixable}
          view={view}
          onChanged={() => {
            setFixOpen(false);
            onChanged();
          }}
        />
      ) : null}
    </>
  );
}

function shortfallText(view: ClientBids): string {
  const short = view.coverage
    .filter((c) => c.eligible < c.needed)
    .map(
      (c) =>
        `${c.slot_label || "A slot"} needs ${String(c.needed - c.eligible)} more eligible ${c.needed - c.eligible === 1 ? "bid" : "bids"}`,
    );
  return short.length > 0 ? `${short.join("; ")}.` : "The team is still short.";
}

function relaxationText(view: ClientBids): string {
  const last = view.relaxations[view.relaxations.length - 1];
  if (!last) return "";
  return `Minimum performance was lowered from ${formatScore(view.thresholds.p0)} to ${formatScore(last.p0)} and competency from ${formatScore(view.thresholds.c0)} to ${formatScore(last.c0)} (step ${String(last.step)} of 3) to find enough candidates.`;
}

function DeveloperCell({ bid }: { bid: ClientBid }) {
  return (
    <span className="flex flex-wrap items-center gap-2">
      <span className="font-medium text-text">{bid.developer_name}</span>
      {bid.is_newcomer ? <NewcomerBadge /> : null}
      {bid.seeded ? <span className="text-caption text-text-subtle">seeded</span> : null}
    </span>
  );
}

function BidTable({ bids, onOpen }: { bids: ClientBid[]; onOpen: (bid: ClientBid) => void }) {
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full text-body-sm">
        <caption className="sr-only">
          Bids with price, days, hours, reputation and the eligibility verdict.
        </caption>
        <thead>
          <tr className="border-b border-border text-left text-text-muted">
            <th scope="col" className="py-2 pr-3 font-medium">
              Developer
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Slot
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Price
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Days
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              <abbr title="Hours a week">Hrs/wk</abbr>
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              <abbr title="Competency">C</abbr>
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              <abbr title="Teamwork">Team</abbr>
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              <abbr title="Performance">P</abbr>
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Eligibility
            </th>
            <th scope="col" className="py-2 pl-3">
              <span className="sr-only">Details</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {bids.map((b) => (
            <tr key={b.id} className="border-b border-border/60 last:border-0">
              <th scope="row" className="py-2 pr-3 text-left font-normal">
                <DeveloperCell bid={b} />
              </th>
              <td className="px-3 py-2 text-text-muted">{b.slot_label}</td>
              <td className="px-3 py-2 text-right tabular">{formatMoney(b.price_paisa)}</td>
              <td className="px-3 py-2 text-right tabular">{b.days_needed}</td>
              <td className="px-3 py-2 text-right tabular">{b.hours_per_week}</td>
              <td className="px-3 py-2 text-right tabular">{formatScore(b.competency)}</td>
              <td className="px-3 py-2 text-right tabular">{formatScore(b.teamwork)}</td>
              <td className="px-3 py-2 text-right tabular">
                {b.is_newcomer ? "—" : formatScore(b.performance)}
              </td>
              <td className="px-3 py-2">
                <Verdict bid={b} />
              </td>
              <td className="py-2 pl-3 text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Why ${b.eligible ? "eligible" : "not eligible"}: ${b.developer_name}`}
                  onClick={() => {
                    onOpen(b);
                  }}
                >
                  Why?
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BidCards({ bids, onOpen }: { bids: ClientBid[]; onOpen: (bid: ClientBid) => void }) {
  return (
    <ul className="space-y-3 md:hidden" aria-label="Bids">
      {bids.map((b) => (
        <li key={b.id} className="rounded-lg border border-border bg-surface p-4">
          <DeveloperCell bid={b} />
          <p className="mt-1 text-body-sm text-text-muted">{b.slot_label}</p>
          <dl className="mt-3 grid grid-cols-3 gap-2 text-body-sm">
            <div>
              <dt className="text-text-muted">Price</dt>
              <dd className="tabular text-text">{formatMoney(b.price_paisa)}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Days</dt>
              <dd className="tabular text-text">{b.days_needed}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Hours a week</dt>
              <dd className="tabular text-text">{b.hours_per_week}</dd>
            </div>
          </dl>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <Verdict bid={b} />
            <Button
              variant="outline"
              onClick={() => {
                onOpen(b);
              }}
              aria-label={`Why ${b.eligible ? "eligible" : "not eligible"}: ${b.developer_name}`}
            >
              Why?
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
