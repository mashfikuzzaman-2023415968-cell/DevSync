/**
 * Project detail + bid sheet (spec §13.5 #11). A developer sees the open project and its slots
 * and places a sealed bid, with a **live eligibility preview** (Algorithm 1 dry-run) that shows,
 * before they submit, whether the bid would be filtered out and why (§9.2). Edit or withdraw an
 * existing bid until the bidding deadline; afterwards the sheet says bidding has closed (the server
 * refuses late changes, D54). The sheet takes the hours a week you commit (§9.17), your expected
 * contribution and up to three of your own portfolio items. Bids are sealed — nothing here reveals
 * other developers' bids (§14.5).
 *
 * The header shows who the client is (signed-in callers only), budget, deadline and team size;
 * the page shows the description, requirements, the roles (yours highlighted), the published
 * plan's milestones and a mini Gantt of its schedule. The role select lists slots needing your
 * skills first and marks the rest "not one of your skills" (Algorithm 1 filters those bids out).
 */
import { CalendarRange, CheckCircle2, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError } from "@/api/client";
import type { EligibilityOut, ProjectDetail } from "@/api/types";
import { Gantt, type GanttEdge } from "@/components/Gantt";
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
  useMyBidsOnProject,
  useUpdateBid,
  useWithdrawBid,
} from "@/features/bids/api";
import { BID_STATUS_TONE, CHECK_LABEL, bidStatusLabel } from "@/features/bids/bidText";
import { useDeveloperProfile, usePortfolio } from "@/features/profile/api";
import { takaProblem, wholeIn } from "@/features/projects/schemas";
import { usePublicProject } from "./api";
import { assessmentKeys, useSlotAssessment, type TimedAssessment } from "@/features/assessment/api";
import { AssessmentRunner } from "@/features/assessment/AssessmentRunner";
import { AssessmentStatusCard, canBid } from "@/features/assessment/AssessmentStatusCard";
import { useBidDraft } from "@/features/assessment/useBidDraft";
import { useQueryClient } from "@tanstack/react-query";

const PREVIEW_DELAY_MS = 500;
const MAX_PORTFOLIO = 3;

export default function ProjectBidPage() {
  const { id = "" } = useParams();
  const project = usePublicProject(id);
  const myBids = useMyBidsOnProject(id);
  const create = useCreateBid(id);
  const withdraw = useWithdrawBid();
  const update = useUpdateBid();
  const [editing, setEditing] = useState(false);
  const preview = useEligibilityPreview(id);

  // The draft survives the role assessment and a reload of this tab (role assessment §11.2).
  const { draft, update: updateDraft, clear: clearDraft } = useBidDraft(id);
  const { slotId, priceTaka, days, proposal, hours } = draft;
  const setSlotId = (slot: string) => {
    updateDraft({ slotId: slot });
  };
  const setPriceTaka = (price: string) => {
    updateDraft({ priceTaka: price });
  };
  const setDays = (value: string) => {
    updateDraft({ days: value });
  };
  const setProposal = (text: string) => {
    updateDraft({ proposal: text });
  };
  const setHours = (value: string) => {
    updateDraft({ hours: value });
  };
  const [running, setRunning] = useState<TimedAssessment | null>(null);
  const qc = useQueryClient();
  const [contribution, setContribution] = useState("");
  const [portfolioIds, setPortfolioIds] = useState<string[]>([]);
  const portfolio = usePortfolio();
  const profile = useDeveloperProfile();
  const [verdict, setVerdict] = useState<EligibilityOut | null>(null);

  // My standing bid here: open, or filtered out when bidding closed (at most one, D49).
  const existing = (myBids.data?.items ?? []).find(
    (b) => b.project_id === id && (b.status === "ACTIVE" || b.status === "INELIGIBLE"),
  );
  const canChange = existing?.status === "ACTIVE";
  const mySkills = new Set((profile.data?.skills ?? []).map((s) => s.skill_id));
  // Slots needing my skills first (stable otherwise), so the right role is the obvious choice.
  const slots = [...(project.data?.slots ?? [])].sort(
    (a, b) => Number(mySkills.has(b.skill_id)) - Number(mySkills.has(a.skill_id)),
  );
  const knowsSkills = profile.isSuccess;
  const chosen = slots.find((s) => s.id === slotId);
  // A newcomer bids on a passed role assessment for the chosen role (§8.3); the server enforces
  // it too, this only keeps the button honest.
  const assessment = useSlotAssessment(id, slotId, Boolean(slotId) && !existing);
  const assessmentAllows = existing ? true : canBid(assessment.data);
  // Field problems with the server's limits (§10 bids), keyed by the server's field names.
  const [serverFields, setServerFields] = useState<Record<string, string>>({});
  const problems: Record<string, string> = {};
  const priceProblem = takaProblem(priceTaka, 0.01);
  if (priceProblem) problems.price_paisa = priceProblem;
  if (days !== "" && !wholeIn(Number(days), 1, 365)) {
    problems.days_needed = "Use a whole number of days from 1 to 365.";
  }
  if (hours !== "" && !wholeIn(Number(hours), 1, 168)) {
    problems.hours_per_week_committed = "Use a whole number of hours from 1 to 168.";
  }
  const fieldError = (key: string): string | undefined => problems[key] ?? serverFields[key];
  const ready =
    slotId && Number(priceTaka) > 0 && Number(days) > 0 && Object.keys(problems).length === 0;
  // Only items still in my portfolio: one deleted since the bid was placed would be refused.
  const ownIds = new Set((portfolio.data ?? []).map((item) => item.id));
  const attached = portfolio.data ? portfolioIds.filter((x) => ownIds.has(x)) : portfolioIds;
  const hoursValue = Number(hours) > 0 ? Number(hours) : undefined;
  // The verdict also depends on the role assessment: passing it (or a retake lock) changes the
  // newcomer rule's answer without any field of the draft changing.
  const previewKey = `${slotId}|${priceTaka}|${days}|${hours}|${assessment.data?.status ?? ""}`;
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
    // previewKey stands for the draft bid fields and the assessment status.
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

  /** Open the sheet on the existing bid, filled in with what was sent. */
  function startEditing() {
    if (!existing) return;
    setSlotId(existing.slot_id);
    setPriceTaka(String(existing.price_paisa / 100));
    setDays(String(existing.days_needed));
    setProposal(existing.proposal);
    setHours(String(existing.hours_per_week_committed));
    setContribution(existing.expected_contribution);
    setPortfolioIds(existing.portfolio_item_ids);
    setServerFields({});
    setEditing(true);
  }

  function saveChanges() {
    if (!existing) return;
    update.mutate(
      {
        bidId: existing.id,
        version: existing.version,
        body: {
          slot_id: slotId,
          price_paisa: Math.round(Number(priceTaka) * 100),
          days_needed: Number(days),
          proposal: proposal.trim(),
          expected_contribution: contribution.trim(),
          portfolio_item_ids: attached,
          ...(hoursValue ? { hours_per_week_committed: hoursValue } : {}),
        },
      },
      {
        onSuccess: () => {
          setEditing(false);
          toast({
            tone: "success",
            title: "Bid updated",
            description: "Only the client can see it.",
          });
        },
        onError: (e) => {
          if (e instanceof ApiError && e.code === "VERSION_CONFLICT") {
            // Changed in another tab: show the saved bid rather than overwrite it.
            setEditing(false);
            void myBids.refetch();
            toast({
              tone: "danger",
              title: "This bid changed elsewhere",
              description: "We’ve loaded the latest version. Check it, then edit again.",
            });
            return;
          }
          if (e instanceof ApiError) setServerFields(e.fields);
          toast({
            tone: "danger",
            title: "Could not update the bid",
            description: e instanceof ApiError ? e.message : "Please try again.",
          });
        },
      },
    );
  }

  function placeBid() {
    create.mutate(
      {
        slot_id: slotId,
        price_paisa: Math.round(Number(priceTaka) * 100),
        days_needed: Number(days),
        proposal: proposal.trim(),
        expected_contribution: contribution.trim(),
        portfolio_item_ids: attached,
        ...(hoursValue ? { hours_per_week_committed: hoursValue } : {}),
      },
      {
        onSuccess: () => {
          clearDraft();
          toast({
            tone: "success",
            title: "Bid placed",
            description: "Only the client can see it.",
          });
        },
        onError: (e) => {
          if (e instanceof ApiError && e.code === "ROLE_ASSESSMENT_REQUIRED") {
            void qc.invalidateQueries({ queryKey: assessmentKeys.status(id, slotId) });
          }
          if (e instanceof ApiError) setServerFields(e.fields);
          toast({
            tone: "danger",
            title:
              e instanceof ApiError && e.code === "LIMIT_REACHED"
                ? "You’re at the open-bid limit"
                : "Could not place the bid",
            description: e instanceof ApiError ? e.message : "Please try again.",
          });
        },
      },
    );
  }

  return (
    <>
      <PageHeader title={p.title} description={p.summary}>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-body-sm sm:flex sm:flex-wrap sm:gap-x-10">
          {p.client ? (
            <div className="col-span-2 min-w-0">
              <dt className="text-text-muted">Client</dt>
              <dd className="break-words font-medium text-text">{p.client.name}</dd>
            </div>
          ) : null}
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
        </dl>
      </PageHeader>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="flex min-w-0 flex-col gap-6">
          <Card>
            <CardHeader title="About this project" />
            <div className="px-5 pb-5">
              {p.description ? (
                <p className="mt-3 whitespace-pre-wrap text-body text-text">{p.description}</p>
              ) : null}
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
                  {slots.map((s) => {
                    const yours = mySkills.has(s.skill_id);
                    return (
                      <li key={s.id}>
                        <Badge tone={yours ? "primary" : "neutral"} icon={yours}>
                          {s.skill} ×{s.count}
                          {yours ? <span className="sr-only"> (your skill)</span> : null}
                        </Badge>
                      </li>
                    );
                  })}
                </ul>
                {slots.some((s) => mySkills.has(s.skill_id)) ? (
                  <p className="mt-2 text-caption text-text-muted">
                    Highlighted roles match skills on your profile.
                  </p>
                ) : null}
              </div>
            </div>
          </Card>
          <PlanCard project={p} />
        </div>

        <Card>
          <CardHeader
            title={existing ? (editing ? "Edit your bid" : "Your bid") : "Place a sealed bid"}
            description="Sealed: only the client sees your price and proposal."
          />
          <div className="px-5 pb-5">
            {myBids.isPending ? (
              <div
                className="mt-4 flex flex-col gap-3"
                aria-busy="true"
                aria-label="Loading your bid"
              >
                <Skeleton className="h-5 w-48" />
                <Skeleton className="h-11 w-full" />
              </div>
            ) : myBids.isError ? (
              <ErrorState
                title="We couldn’t check whether you’ve bid"
                requestId={myBids.error instanceof ApiError ? myBids.error.requestId : null}
                onRetry={() => void myBids.refetch()}
              />
            ) : existing && !(editing && p.open_for_bids && canChange) ? (
              <div className="mt-4">
                <p className="text-body-sm text-text">
                  You bid {formatMoney(existing.price_paisa)} over{" "}
                  {formatDays(existing.days_needed)}.
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <Badge tone={BID_STATUS_TONE[existing.status] ?? "neutral"}>
                    {bidStatusLabel(existing.status)}
                  </Badge>
                  <Link
                    to={`/dev/bids/${existing.id}`}
                    className="inline-flex min-h-11 items-center text-body-sm font-medium text-primary hover:underline"
                  >
                    See bid details
                  </Link>
                </div>
                {p.open_for_bids && canChange ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={startEditing}>
                      Edit bid
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      loading={withdraw.isPending}
                      onClick={() => {
                        withdraw.mutate(
                          { bidId: existing.id, version: existing.version },
                          {
                            onSuccess: () => {
                              toast({ tone: "success", title: "Bid withdrawn" });
                            },
                            onError: (e) => {
                              const conflict =
                                e instanceof ApiError && e.code === "VERSION_CONFLICT";
                              toast({
                                tone: "danger",
                                title: conflict
                                  ? "This bid changed elsewhere"
                                  : "Could not withdraw the bid",
                                description: conflict
                                  ? "We’ve loaded the latest version. Check it, then try again."
                                  : e instanceof ApiError
                                    ? e.message
                                    : "Please try again.",
                              });
                            },
                          },
                        );
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
                      options={slots.map((s) => {
                        const base = s.label ? `${s.skill}: ${s.label}` : s.skill;
                        return {
                          value: s.id,
                          label:
                            knowsSkills && !mySkills.has(s.skill_id)
                              ? `${base} (not one of your skills)`
                              : base,
                        };
                      })}
                      placeholder="Choose a role"
                    />
                  )}
                </FormField>
                {chosen && !existing ? (
                  <AssessmentStatusCard projectId={id} slotId={chosen.id} onRun={setRunning} />
                ) : null}
                {knowsSkills && chosen && !mySkills.has(chosen.skill_id) ? (
                  <Alert tone="warning" title="Not one of your skills">
                    {`This role needs ${chosen.skill}, which isn’t on your profile, so the bid would be filtered out. Add the skill to your profile, or choose a role that matches your skills.`}
                  </Alert>
                ) : null}
                <div className="grid grid-cols-2 gap-4">
                  <Field
                    label="Your price (৳)"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    error={fieldError("price_paisa")}
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
                    error={fieldError("days_needed")}
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
                    error={fieldError("hours_per_week_committed")}
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
                            disabled={!checked && attached.length >= MAX_PORTFOLIO}
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

                {existing ? (
                  <div className="flex flex-wrap gap-2">
                    <Button loading={update.isPending} disabled={!ready} onClick={saveChanges}>
                      Save changes
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setEditing(false);
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    <Button
                      loading={create.isPending}
                      disabled={!ready || !assessmentAllows}
                      onClick={placeBid}
                    >
                      Place sealed bid
                    </Button>
                    {ready && !assessmentAllows && assessment.data ? (
                      <p className="text-body-sm text-text-muted">
                        Pass the role assessment above to place this bid.
                      </p>
                    ) : null}
                  </div>
                )}
              </div>
            )}
          </div>
        </Card>
      </div>
      {running ? (
        <AssessmentRunner
          attempt={running}
          onClose={() => {
            setRunning(null);
            void qc.invalidateQueries({ queryKey: assessmentKeys.status(id, slotId) });
          }}
        />
      ) : null}
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

function statusLabel(status: string): string {
  const words = status.toLowerCase().replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The published plan: milestones with durations and states, and a mini Gantt (§13.5 #11). */
function PlanCard({ project }: { project: ProjectDetail }) {
  const schedule = project.schedule;
  const edges = useMemo<GanttEdge[]>(
    () => (schedule?.edges ?? []).map((e): GanttEdge => [e.predecessor, e.successor]),
    [schedule],
  );
  return (
    <Card>
      <CardHeader
        title="Plan"
        description={
          schedule
            ? `${String(project.milestones.length)} milestones over ${formatDays(schedule.duration)}. Critical milestones are in rose.`
            : undefined
        }
      />
      <div className="px-5 pb-5">
        {project.milestones.length === 0 ? (
          <EmptyState
            icon={<CalendarRange />}
            title="No plan shared yet"
            description="The client hasn’t published milestones for this project."
          />
        ) : (
          <>
            <ol className="mt-3 flex flex-col divide-y divide-border" aria-label="Milestones">
              {project.milestones.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="min-w-0 break-words text-body-sm font-medium text-text">
                    {m.name}
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="text-body-sm tabular text-text-muted">
                      {formatDays(m.duration_days)}
                    </span>
                    <Badge tone="neutral" icon={false}>
                      {statusLabel(m.status)}
                    </Badge>
                  </span>
                </li>
              ))}
            </ol>
            {schedule && schedule.nodes.length > 0 ? (
              <div className="mt-4">
                <Gantt
                  nodes={schedule.nodes}
                  edges={edges}
                  startDate={project.start_date ?? null}
                  deadlineDays={project.deadline_days}
                />
              </div>
            ) : null}
          </>
        )}
      </div>
    </Card>
  );
}
