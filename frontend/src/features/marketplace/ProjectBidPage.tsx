/**
 * Project detail + bid sheet (spec §13.5 #11). A developer sees the open project and its slots
 * and places a sealed bid, with a **live eligibility preview** (Algorithm 1 dry-run) that shows,
 * before they submit, whether the bid would be filtered out and why (§9.2). Edit or withdraw an
 * existing bid until the bidding deadline; afterwards the sheet says bidding has closed (the server
 * refuses late changes, D54). The sheet takes the hours a week you commit (§9.17), your expected
 * contribution and up to three of your own portfolio items. Bids are sealed — nothing here reveals
 * other developers' bids (§14.5).
 */
import { CheckCircle2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { ApiError } from "@/api/client";
import type { EligibilityOut } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { Alert, EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { Checkbox } from "@/components/ui/Choice";
import { Field, FormField, Textarea } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { toast } from "@/components/ui/toast-store";
import { formatDate, formatDays, formatMoney } from "@/lib/format";
import {
  useCreateBid,
  useEligibilityPreview,
  useMyBids,
  useWithdrawBid,
} from "@/features/bids/api";
import { CHECK_LABEL } from "@/features/bids/bidText";
import { usePortfolio } from "@/features/profile/api";
import { usePublicProject } from "./api";

const PREVIEW_DELAY_MS = 500;
const MAX_PORTFOLIO = 3;

export default function ProjectBidPage() {
  const { id = "" } = useParams();
  const project = usePublicProject(id);
  const myBids = useMyBids();
  const create = useCreateBid(id);
  const withdraw = useWithdrawBid();
  const preview = useEligibilityPreview(id);

  const [slotId, setSlotId] = useState("");
  const [priceTaka, setPriceTaka] = useState("");
  const [days, setDays] = useState("");
  const [proposal, setProposal] = useState("");
  const [hours, setHours] = useState("");
  const [contribution, setContribution] = useState("");
  const [portfolioIds, setPortfolioIds] = useState<string[]>([]);
  const portfolio = usePortfolio();
  const [verdict, setVerdict] = useState<EligibilityOut | null>(null);

  const existing = (myBids.data ?? []).find((b) => b.project_id === id && b.status === "ACTIVE");
  const slots = project.data?.slots ?? [];
  const ready = slotId && Number(priceTaka) > 0 && Number(days) > 0;
  const hoursValue = Number(hours) > 0 ? Number(hours) : undefined;
  const previewKey = `${slotId}|${priceTaka}|${days}|${hours}`;
  const runPreview = preview.mutate;

  // Debounced live eligibility preview as the developer edits the draft bid.
  useEffect(() => {
    if (!ready) {
      setVerdict(null);
      return undefined;
    }
    const timer = window.setTimeout(() => {
      runPreview(
        {
          slot_id: slotId,
          price_paisa: Math.round(Number(priceTaka) * 100),
          days_needed: Number(days),
          ...(hoursValue ? { hours_per_week_committed: hoursValue } : {}),
        },
        { onSuccess: setVerdict },
      );
    }, PREVIEW_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
    };
    // previewKey stands for the draft bid fields.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewKey, ready, runPreview]);

  if (project.isLoading) {
    return (
      <>
        <PageHeader title="Project" />
        <Card>
          <Skeleton className="h-48 w-full" />
        </Card>
      </>
    );
  }
  if (project.isError || !project.data) {
    const err = project.error;
    return (
      <>
        <PageHeader title="Project" />
        <Card>
          <ErrorState
            title="We couldn’t load this project"
            requestId={err instanceof ApiError ? err.requestId : null}
            onRetry={() => void project.refetch()}
          />
        </Card>
      </>
    );
  }

  const p = project.data;

  function placeBid() {
    create.mutate(
      {
        slot_id: slotId,
        price_paisa: Math.round(Number(priceTaka) * 100),
        days_needed: Number(days),
        proposal: proposal.trim(),
        expected_contribution: contribution.trim(),
        portfolio_item_ids: portfolioIds,
        ...(hoursValue ? { hours_per_week_committed: hoursValue } : {}),
      },
      {
        onSuccess: () => {
          toast({
            tone: "success",
            title: "Bid placed",
            description: "Only the client can see it.",
          });
        },
        onError: (e) => {
          toast({
            tone: "danger",
            title: "Could not place the bid",
            description: e instanceof ApiError ? e.message : "Please try again.",
          });
        },
      },
    );
  }

  return (
    <>
      <PageHeader title={p.title} description={p.summary} />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <Card>
          <CardHeader title="About this project" />
          <div className="px-5 pb-5">
            <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 text-body-sm">
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
                <dd className="font-medium text-text">{p.team_size}</dd>
              </div>
            </dl>
            {p.requirements ? (
              <div className="mt-4">
                <h3 className="text-body-sm font-semibold text-text">Requirements</h3>
                <p className="mt-1 whitespace-pre-wrap text-body-sm text-text-muted">
                  {p.requirements}
                </p>
              </div>
            ) : null}
            <div className="mt-4">
              <h3 className="text-body-sm font-semibold text-text">Roles</h3>
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {slots.map((s) => (
                  <li key={s.id}>
                    <Badge tone="neutral">
                      {s.skill} ×{s.count}
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title={existing ? "Your bid" : "Place a sealed bid"}
            description="Sealed: only the client sees your price and proposal."
          />
          <div className="px-5 pb-5">
            {existing ? (
              <div className="mt-4">
                <p className="text-body-sm text-text">
                  You bid {formatMoney(existing.price_paisa)} over{" "}
                  {formatDays(existing.days_needed)}.
                </p>
                <Badge tone={existing.status === "ACTIVE" ? "info" : "neutral"} className="mt-2">
                  {existing.status.charAt(0) + existing.status.slice(1).toLowerCase()}
                </Badge>
                {p.open_for_bids ? (
                  <div className="mt-4">
                    <Button
                      variant="destructive"
                      size="sm"
                      loading={withdraw.isPending}
                      onClick={() => {
                        withdraw.mutate(existing.id, {
                          onSuccess: () => {
                            toast({ tone: "success", title: "Bid withdrawn" });
                          },
                        });
                      }}
                    >
                      Withdraw bid
                    </Button>
                  </div>
                ) : (
                  <p className="mt-4 text-body-sm text-text-muted">
                    Bidding has closed, so this bid can no longer be changed.
                  </p>
                )}
              </div>
            ) : !p.open_for_bids ? (
              <Alert tone="info" title="Bidding has closed" className="mt-4">
                {p.bidding_deadline
                  ? `This project stopped taking bids on ${formatDate(p.bidding_deadline)}.`
                  : "This project isn’t taking bids."}
              </Alert>
            ) : slots.length === 0 ? (
              <EmptyState
                title="No open roles"
                description="This project has no slots to bid on."
              />
            ) : (
              <div className="mt-4 flex flex-col gap-4">
                <FormField label="Role">
                  {(a11y) => (
                    <Select
                      {...a11y}
                      value={slotId || undefined}
                      onChange={setSlotId}
                      options={slots.map((s) => ({
                        value: s.id,
                        label: s.label ? `${s.skill}: ${s.label}` : s.skill,
                      }))}
                      placeholder="Choose a role"
                    />
                  )}
                </FormField>
                <div className="grid grid-cols-2 gap-4">
                  <Field
                    label="Your price (৳)"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    value={priceTaka}
                    onChange={(e) => {
                      setPriceTaka(e.target.value);
                    }}
                  />
                  <Field
                    label="Days you need"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={365}
                    value={days}
                    onChange={(e) => {
                      setDays(e.target.value);
                    }}
                  />
                </div>
                <FormField label="Proposal">
                  {(a11y) => (
                    <Textarea
                      {...a11y}
                      value={proposal}
                      onChange={(e) => {
                        setProposal(e.target.value);
                      }}
                      rows={3}
                      maxLength={3000}
                      placeholder="How you'll approach the work."
                    />
                  )}
                </FormField>

                <div className="grid grid-cols-2 gap-4">
                  <Field
                    label="Hours a week"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={168}
                    hint="Defaults to 20 or your profile hours."
                    value={hours}
                    onChange={(e) => {
                      setHours(e.target.value);
                    }}
                  />
                  <Field
                    label="Expected contribution"
                    maxLength={500}
                    value={contribution}
                    onChange={(e) => {
                      setContribution(e.target.value);
                    }}
                  />
                </div>
                {portfolio.data && portfolio.data.length > 0 ? (
                  <fieldset>
                    <legend className="text-body-sm font-medium text-text">
                      Portfolio items (up to {MAX_PORTFOLIO})
                    </legend>
                    <div className="mt-2 flex flex-col gap-1">
                      {portfolio.data.map((item) => {
                        const checked = portfolioIds.includes(item.id);
                        return (
                          <Checkbox
                            key={item.id}
                            label={item.title}
                            checked={checked}
                            disabled={!checked && portfolioIds.length >= MAX_PORTFOLIO}
                            onCheckedChange={(on) => {
                              setPortfolioIds((ids) =>
                                on === true ? [...ids, item.id] : ids.filter((x) => x !== item.id),
                              );
                            }}
                          />
                        );
                      })}
                    </div>
                  </fieldset>
                ) : null}

                {verdict ? <EligibilityPreview verdict={verdict} /> : null}

                <Button loading={create.isPending} disabled={!ready} onClick={placeBid}>
                  Place sealed bid
                </Button>
              </div>
            )}
          </div>
        </Card>
      </div>
    </>
  );
}

function EligibilityPreview({ verdict }: { verdict: EligibilityOut }) {
  return (
    <Alert tone={verdict.eligible ? "success" : "warning"} title={verdict.message}>
      <ul className="mt-1 flex flex-col gap-1">
        {verdict.checks.map((c) => (
          <li key={c.name} className="flex items-start gap-2 text-body-sm">
            {c.ok ? (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
            ) : (
              <XCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
            )}
            <span>
              {CHECK_LABEL[c.name] ?? c.name}
              <span className="block text-text-muted">{c.detail}</span>
            </span>
          </li>
        ))}
      </ul>
    </Alert>
  );
}
