/**
 * Bid detail `/dev/bids/:id` (spec §13.5 #12): one of my sealed bids — the project it is on,
 * what I offered, the status timeline (Submitted → Evaluated → Selected / Not selected →
 * Accepted) and, when bidding closed and the filter left it out, why in plain words with a hint.
 * While bidding is open the page shows how the bid stands against the project's own requirements
 * (never against other bids) and offers Edit (the bid sheet) and Withdraw (with the bid's version,
 * so a change made in another tab is not overwritten). Someone else's bid is a 404 from the
 * server, shown as "not found". The "why not selected" card arrives with team formation (Phase 7).
 */
import { CheckCircle2, Circle, CircleDot, XCircle } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router";
import { ApiError } from "@/api/client";
import type { BidDetail } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { Alert, EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { ConfirmDialog } from "@/components/ui/Overlay";
import { toast } from "@/components/ui/toast-store";
import { formatDate, formatDateTime, formatDays, formatMoney } from "@/lib/format";
import { useBid, useWithdrawBid } from "./api";
import { BID_STATUS_TONE, CHECK_LABEL, bidStatusLabel, bidSteps, type BidStep } from "./bidText";

export default function BidDetailPage() {
  const { id = "" } = useParams();
  const bid = useBid(id);

  if (bid.isPending) {
    return (
      <>
        <PageHeader title="Your bid" />
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
          <Card className="p-5" aria-busy="true" aria-label="Loading your bid">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="mt-4 h-24 w-full" />
          </Card>
          <Card className="p-5">
            <Skeleton className="h-32 w-full" />
          </Card>
        </div>
      </>
    );
  }
  if (bid.isError) {
    const err = bid.error;
    if (err instanceof ApiError && err.status === 404) {
      return (
        <>
          <PageHeader title="Bid not found" />
          <Card>
            <EmptyState
              title="We couldn’t find that bid"
              description="It may have been removed, or it isn’t one of yours."
              action={
                <Button asChild variant="outline">
                  <Link to="/dev/bids">Back to my bids</Link>
                </Button>
              }
            />
          </Card>
        </>
      );
    }
    return (
      <>
        <PageHeader title="Your bid" />
        <Card>
          <ErrorState
            title="Your bid didn’t load"
            requestId={err instanceof ApiError ? err.requestId : null}
            onRetry={() => void bid.refetch()}
          />
        </Card>
      </>
    );
  }

  const b = bid.data;
  return (
    <>
      <PageHeader
        title={b.project.title}
        description={`Your sealed bid for ${b.slot_label}. Only the client can see it.`}
        action={
          <Button asChild variant="outline">
            <Link to="/dev/bids">All my bids</Link>
          </Button>
        }
      />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <div className="flex min-w-0 flex-col gap-6">
          {b.status === "INELIGIBLE" ? <WhyFiltered bid={b} /> : null}
          {b.eligibility ? <Standing bid={b} /> : null}
          <OfferCard bid={b} />
        </div>
        <div className="flex min-w-0 flex-col gap-6">
          <StatusCard bid={b} onChanged={() => void bid.refetch()} />
          <ProjectCard bid={b} />
        </div>
      </div>
    </>
  );
}

function WhyFiltered({ bid }: { bid: BidDetail }) {
  const reasons = bid.reasons ?? [];
  return (
    <Alert tone="warning" title="Why this bid was filtered out">
      {reasons.length === 0 ? (
        <p>It didn’t meet this project’s requirements when bidding closed.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {reasons.map((r) => (
            <li key={r.code}>
              <p>{r.text}</p>
              <p className="text-text-muted">{r.hint}</p>
            </li>
          ))}
        </ul>
      )}
    </Alert>
  );
}

function Standing({ bid }: { bid: BidDetail }) {
  const e = bid.eligibility;
  if (!e) return null;
  return (
    <Card>
      <CardHeader
        title="How your bid stands"
        description="Checked against this project’s requirements now. It’s final when bidding closes."
      />
      <div className="px-5 pb-5">
        <Alert tone={e.eligible ? "success" : "warning"} className="mt-4">
          {e.message}
        </Alert>
        <ul className="mt-4 flex flex-col gap-2">
          {e.checks.map((c) => (
            <li key={c.name} className="flex items-start gap-2 text-body-sm">
              {c.ok ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
              ) : (
                <XCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
              )}
              <span>
                <span className="sr-only">{c.ok ? "Met: " : "Not met: "}</span>
                <span className="text-text">{CHECK_LABEL[c.name] ?? c.name}</span>{" "}
                <span className="text-text-muted">{c.detail}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}

function OfferCard({ bid }: { bid: BidDetail }) {
  const rows: [string, string][] = [
    ["Role", bid.slot_label],
    ["Price", formatMoney(bid.price_paisa)],
    ["Days needed", formatDays(bid.days_needed)],
    ["Hours a week", `${String(bid.hours_per_week_committed)} hours`],
    ["Submitted", formatDateTime(bid.created_at)],
  ];
  if (bid.updated_at !== bid.created_at)
    rows.push(["Last changed", formatDateTime(bid.updated_at)]);
  return (
    <Card>
      <CardHeader title="What you offered" />
      <div className="px-5 pb-5">
        <dl className="mt-4 grid grid-cols-1 gap-x-6 gap-y-3 text-body-sm sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-text-muted">{label}</dt>
              <dd className="break-words font-medium tabular text-text">{value}</dd>
            </div>
          ))}
        </dl>
        <h3 className="mt-5 text-body-sm font-semibold text-text">Proposal</h3>
        <p className="mt-1 whitespace-pre-wrap break-words text-body-sm text-text-muted">
          {bid.proposal || "No proposal written."}
        </p>
        {bid.expected_contribution ? (
          <>
            <h3 className="mt-4 text-body-sm font-semibold text-text">Expected contribution</h3>
            <p className="mt-1 whitespace-pre-wrap break-words text-body-sm text-text-muted">
              {bid.expected_contribution}
            </p>
          </>
        ) : null}
        {bid.portfolio.length > 0 ? (
          <>
            <h3 className="mt-4 text-body-sm font-semibold text-text">Portfolio attached</h3>
            <ul className="mt-1 list-disc pl-5 text-body-sm text-text-muted">
              {bid.portfolio.map((item) => (
                <li key={item.id}>{item.title}</li>
              ))}
            </ul>
          </>
        ) : null}
      </div>
    </Card>
  );
}

const STEP_ICON: Record<BidStep["state"], typeof Circle> = {
  done: CheckCircle2,
  current: CircleDot,
  upcoming: Circle,
  stopped: XCircle,
};
const STEP_TONE: Record<BidStep["state"], string> = {
  done: "text-success",
  current: "text-primary",
  upcoming: "text-text-subtle",
  stopped: "text-text-muted",
};
const STEP_SR: Record<BidStep["state"], string> = {
  done: "Done",
  current: "In progress",
  upcoming: "Not yet",
  stopped: "Stopped",
};

function StatusCard({ bid, onChanged }: { bid: BidDetail; onChanged: () => void }) {
  const withdraw = useWithdrawBid();
  const navigate = useNavigate();
  const steps = bidSteps(bid.status, Boolean(bid.evaluated_at));
  return (
    <Card>
      <CardHeader
        title="Status"
        action={
          <Badge tone={BID_STATUS_TONE[bid.status] ?? "neutral"}>
            {bidStatusLabel(bid.status)}
          </Badge>
        }
      />
      <div className="px-5 pb-5">
        <ol className="mt-4 flex flex-col gap-3">
          {steps.map((s) => {
            const Icon = STEP_ICON[s.state];
            return (
              <li key={s.label} className="flex items-start gap-2 text-body-sm">
                <Icon
                  className={`mt-0.5 size-4 shrink-0 ${STEP_TONE[s.state]}`}
                  aria-hidden="true"
                />
                <span>
                  <span className="sr-only">{STEP_SR[s.state]}: </span>
                  <span className="font-medium text-text">{s.label}</span>
                  {s.note ? <span className="block text-text-muted">{s.note}</span> : null}
                </span>
              </li>
            );
          })}
        </ol>
        {bid.can_edit || bid.can_withdraw ? (
          <div className="mt-5 flex flex-wrap gap-2">
            {bid.can_edit ? (
              <Button asChild variant="outline" size="sm">
                <Link to={`/dev/projects/${bid.project.id}`}>Edit bid</Link>
              </Button>
            ) : null}
            {bid.can_withdraw ? (
              <ConfirmDialog
                trigger={
                  <Button variant="destructive" size="sm">
                    Withdraw bid
                  </Button>
                }
                title="Withdraw this bid?"
                description="The client will no longer see it. You can place a new bid while bidding is open."
                confirmLabel="Withdraw bid"
                onConfirm={() =>
                  withdraw
                    .mutateAsync({ bidId: bid.id, version: bid.version })
                    .then(() => {
                      toast({ tone: "success", title: "Bid withdrawn" });
                      void navigate("/dev/bids");
                    })
                    .catch((e: unknown) => {
                      const conflict = e instanceof ApiError && e.code === "VERSION_CONFLICT";
                      toast({
                        tone: "danger",
                        title: conflict ? "This bid changed elsewhere" : "Could not withdraw",
                        description: conflict
                          ? "We’ve loaded the latest version. Check it, then try again."
                          : e instanceof ApiError
                            ? e.message
                            : "Please try again.",
                      });
                      onChanged();
                    })
                }
              />
            ) : null}
          </div>
        ) : bid.status === "ACTIVE" || bid.status === "INELIGIBLE" ? (
          <p className="mt-5 text-body-sm text-text-muted">
            Bidding has closed, so this bid can no longer be changed.
          </p>
        ) : null}
      </div>
    </Card>
  );
}

function ProjectCard({ bid }: { bid: BidDetail }) {
  const p = bid.project;
  return (
    <Card>
      <CardHeader title="The project" description={p.summary || undefined} />
      <div className="px-5 pb-5">
        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-body-sm">
          <div>
            <dt className="text-text-muted">Budget</dt>
            <dd className="font-medium tabular text-text">{formatMoney(p.budget_paisa)}</dd>
          </div>
          <div>
            <dt className="text-text-muted">Deadline</dt>
            <dd className="font-medium text-text">{formatDays(p.deadline_days)}</dd>
          </div>
          <div>
            <dt className="text-text-muted">Team size</dt>
            <dd className="font-medium text-text">{p.team_size} people</dd>
          </div>
          {p.bidding_deadline ? (
            <div>
              <dt className="text-text-muted">
                {p.open_for_bids ? "Bidding closes" : "Bidding closed"}
              </dt>
              <dd className="font-medium text-text">{formatDate(p.bidding_deadline)}</dd>
            </div>
          ) : null}
        </dl>
        {p.status === "BIDDING" ? (
          <Button asChild variant="ghost" size="sm" className="mt-4">
            <Link to={`/dev/projects/${p.id}`}>View project</Link>
          </Button>
        ) : null}
      </div>
    </Card>
  );
}
