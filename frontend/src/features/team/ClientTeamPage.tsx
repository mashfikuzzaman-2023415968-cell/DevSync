/**
 * Client Team `/client/projects/:id/team` (spec §13.5 #25, §1.6; D118–D138).
 *
 * - Members and invitations: status, a live countdown for pending ones, "can't accept: fully
 *   booked" (D124), price and days, competency and teamwork 0–100, newcomer and lead badges.
 * - The lead: the system's recommendation with its reason (§1.6 rule 1), a selector of accepted
 *   members, "Confirm lead"; after the start "Change lead" with a reason.
 * - "Start project", disabled with plain reasons until every place is accepted and a lead chosen.
 * - Team repair: while computing the swarm indicator; then the impact and the top three
 *   candidates with "Invite"; with nobody, the reasons with "Reopen place (48 h)" and
 *   "Raise budget".
 * - Lead-change requests (approve / reject with a reason) and removal requests.
 */
import { Crown, Users } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError } from "@/api/client";
import type { RepairOut, TeamForClient, TeamMemberForClient } from "@/api/types";
import { SwarmIndicator } from "@/components/ConvergenceChart";
import { ExpiryCountdown } from "@/components/ExpiryCountdown";
import { ReasonDialog } from "@/components/ReasonDialog";
import { Button } from "@/components/ui/Button";
import {
  Avatar,
  Badge,
  Breadcrumbs,
  Card,
  CardHeader,
  NewcomerBadge,
  Skeleton,
} from "@/components/ui/Display";
import { FormField, Input } from "@/components/ui/Field";
import { Alert, EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { ConfirmDialog, Dialog } from "@/components/ui/Overlay";
import { Select } from "@/components/ui/Select";
import { toast } from "@/components/ui/toast-store";
import { formatDays, formatMoney } from "@/lib/format";
import {
  useChooseLead,
  useChooseReplacement,
  useDecideLeadChange,
  useRaiseBudget,
  useReopenSlot,
  useRepair,
  useStartProject,
  useTeam,
} from "./api";
import { memberStatus, score } from "./teamText";

const OPEN_REPAIR = new Set(["COMPUTING", "READY", "NO_CANDIDATES"]);

export default function ClientTeamPage() {
  const { id = "" } = useParams();
  const team = useTeam(id);
  if (team.isPending) {
    return (
      <>
        <PageHeader title="Your team" />
        <div className="grid gap-4 md:grid-cols-2" aria-busy="true" aria-label="Loading your team">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </>
    );
  }
  if (team.isError) {
    const err = team.error;
    if (err instanceof ApiError && err.status === 404) {
      return (
        <>
          <PageHeader title="Your team" />
          <Card>
            <EmptyState
              icon={<Users />}
              title="No team yet"
              description="A team appears here once you confirm one on the team formation page."
              action={
                <Button asChild variant="outline">
                  <Link to={`/client/projects/${id}/formation`}>Go to team formation</Link>
                </Button>
              }
            />
          </Card>
        </>
      );
    }
    return (
      <>
        <PageHeader title="Your team" />
        <Card>
          <ErrorState
            title="Your team didn’t load"
            requestId={err instanceof ApiError ? err.requestId : null}
            onRetry={() => void team.refetch()}
          />
        </Card>
      </>
    );
  }
  if (team.data.view !== "client") return null;
  return <TeamView team={team.data} />;
}

function TeamView({ team }: { team: TeamForClient }) {
  const started = team.project_status === "IN_PROGRESS";
  const repairOpen = team.repair !== null && OPEN_REPAIR.has(team.repair.status);
  return (
    <>
      <PageHeader
        title="Your team"
        breadcrumbs={
          <Breadcrumbs
            items={[
              { label: "My projects", to: "/client/projects" },
              { label: team.project_title, to: `/client/projects/${team.project_id}/bids` },
              { label: "Team" },
            ]}
          />
        }
        description={
          started
            ? `“${team.project_title}” is in progress.`
            : `Invitations for “${team.project_title}”. The project starts when every place is accepted and you choose a lead.`
        }
        action={
          started ? (
            <Button asChild>
              <Link to={`/w/${team.project_id}/team`}>Open workspace</Link>
            </Button>
          ) : null
        }
      />
      {team.team_status === "CANCELLED" ? (
        <Alert tone="info" title="This team was cancelled" className="mb-6">
          The project was cancelled before it started, so every invitation and reservation was
          released.
        </Alert>
      ) : null}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <div className="flex min-w-0 flex-col gap-6">
          {repairOpen && team.repair ? <RepairPanel team={team} /> : null}
          <Members team={team} />
        </div>
        <div className="flex min-w-0 flex-col gap-6">
          {team.team_status !== "CANCELLED" ? <LeadCard team={team} /> : null}
          {team.project_status === "TEAM_PENDING" ? <StartCard team={team} /> : null}
          <Requests team={team} />
        </div>
      </div>
    </>
  );
}

function Members({ team }: { team: TeamForClient }) {
  return (
    <Card>
      <CardHeader title="Members and invitations" />
      <ul className="divide-y divide-border px-5 pb-2">
        {team.members.map((m) => (
          <MemberRow key={m.id} member={m} />
        ))}
      </ul>
    </Card>
  );
}

function MemberRow({ member: m }: { member: TeamMemberForClient }) {
  const status = memberStatus(m.status);
  const pending = m.invitation?.state === "PENDING";
  return (
    <li className="flex flex-col gap-3 py-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <Avatar name={m.developer_name} newcomer={m.is_newcomer} />
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 font-medium text-text">
            {m.developer_name}
            {m.is_lead ? (
              <Badge tone="info" icon={false}>
                <Crown className="size-3.5" aria-hidden="true" /> Lead
              </Badge>
            ) : null}
            {m.is_newcomer ? <NewcomerBadge /> : null}
          </p>
          <p className="text-body-sm text-text-muted">
            {m.slot_label}, {formatMoney(m.price_paisa)} in {formatDays(m.days_needed)}
          </p>
          <p className="text-caption text-text-muted">
            Competency {score(m.competency)}, teamwork {score(m.teamwork)}, {m.hours_per_week} hours
            a week
          </p>
          {m.fully_booked ? (
            <p className="mt-1 text-body-sm font-medium text-warning">
              Can’t accept: fully booked over this project’s dates
            </p>
          ) : null}
          {m.left_reason && (m.status === "LEFT" || m.status === "REMOVED") ? (
            <p className="mt-1 text-body-sm text-text-muted">Reason: {m.left_reason}</p>
          ) : null}
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-start gap-1 sm:items-end">
        <Badge tone={status.tone}>
          {m.status === "INVITED" && m.invitation?.state === "UNSENT"
            ? "Not sent yet"
            : status.label}
        </Badge>
        {pending && m.invitation?.expires_at ? (
          <ExpiryCountdown expiresAt={m.invitation.expires_at} />
        ) : null}
      </div>
    </li>
  );
}

function LeadCard({ team }: { team: TeamForClient }) {
  const choose = useChooseLead(team.project_id);
  const started = team.project_status === "IN_PROGRESS";
  const active = team.members.filter((m) => m.status === "ACTIVE" && !m.lead_declined);
  const lead = team.members.find((m) => m.id === team.lead_member_id);
  const rec = team.recommendation;
  const [picked, setPicked] = useState<string | undefined>(undefined);
  const value = picked ?? rec?.preselected_member_id ?? rec?.member_id;
  const error = choose.error instanceof ApiError ? choose.error.message : null;
  return (
    <Card>
      <CardHeader title="Team lead" />
      <div className="space-y-4 px-5 pb-5 pt-3 text-body-sm">
        {lead ? (
          <p className="flex items-center gap-2 text-text">
            <Crown className="size-4 text-info" aria-hidden="true" />
            {lead.developer_name} leads the team.
          </p>
        ) : null}
        {rec ? (
          <div className="rounded-lg bg-surface-2 p-4">
            <p className="font-semibold text-text">Recommended: {rec.developer_name}</p>
            <p className="mt-1 text-text-muted">{rec.reason}</p>
          </div>
        ) : !lead ? (
          <p className="text-text-muted">
            DevSync recommends a lead once every place is accepted. You make the final choice.
          </p>
        ) : null}
        {team.can_choose_lead && active.length > 0 && (!lead || started) ? (
          <>
            <FormField label={lead ? "New lead" : "Choose the lead"}>
              <Select
                value={value}
                onChange={setPicked}
                options={active.map((m) => ({ value: m.id, label: m.developer_name }))}
                placeholder="Choose an accepted member"
              />
            </FormField>
            {started ? (
              <ReasonDialog
                trigger={<Button disabled={!value || value === lead?.id}>Change lead</Button>}
                title="Change the team lead?"
                description="The team is told. Give a reason; it is recorded."
                label="Reason"
                actionLabel="Change lead"
                onSubmit={(reason) =>
                  choose
                    .mutateAsync({ memberId: value ?? "", version: team.project_version, reason })
                    .then(() => {
                      toast({ tone: "success", title: "Team lead changed" });
                    })
                }
              />
            ) : (
              <Button
                disabled={!value}
                loading={choose.isPending}
                onClick={() => {
                  if (!value) return;
                  choose.mutate(
                    { memberId: value, version: team.project_version },
                    {
                      onSuccess: () => {
                        toast({ tone: "success", title: "Team lead chosen" });
                      },
                    },
                  );
                }}
              >
                Confirm lead
              </Button>
            )}
            {error ? (
              <p className="text-danger" role="alert">
                {error}
              </p>
            ) : null}
          </>
        ) : null}
      </div>
    </Card>
  );
}

function StartCard({ team }: { team: TeamForClient }) {
  const start = useStartProject(team.project_id);
  const error = start.error instanceof ApiError ? start.error.message : null;
  return (
    <Card>
      <CardHeader title="Start the project" />
      <div className="space-y-3 px-5 pb-5 pt-3 text-body-sm">
        {team.start_blockers.length > 0 ? (
          <ul className="list-disc space-y-1 pl-5 text-text-muted">
            {team.start_blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        ) : (
          <p className="text-text">
            Every place is accepted and the lead is chosen. Starting opens the workspace and the
            first milestones.
          </p>
        )}
        <ConfirmDialog
          destructive={false}
          title="Start the project?"
          description="It starts today (or on its planned date if later). The team is told and the workspace opens."
          confirmLabel="Start project"
          onConfirm={async () => {
            await start.mutateAsync(team.project_version);
            toast({ tone: "success", title: "Project started" });
          }}
          trigger={<Button disabled={!team.can_start}>Start project</Button>}
        />
        {error ? (
          <p className="text-danger" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </Card>
  );
}

function RepairPanel({ team }: { team: TeamForClient }) {
  const q = useRepair(team.project_id, true);
  if (q.isPending) {
    return (
      <Card className="p-5">
        <Skeleton className="h-24 w-full" />
      </Card>
    );
  }
  if (q.isError) {
    return (
      <Card>
        <ErrorState
          title="Team repair didn’t load"
          requestId={q.error instanceof ApiError ? q.error.requestId : null}
          onRetry={() => void q.refetch()}
        />
      </Card>
    );
  }
  return <Repair team={team} repair={q.data} />;
}

function Repair({ team, repair }: { team: TeamForClient; repair: RepairOut }) {
  const choose = useChooseReplacement(team.project_id);
  const reopen = useReopenSlot(team.project_id);
  const affected = (repair.impact?.["affected_milestones"] as string[] | undefined) ?? [];
  const error = [choose.error, reopen.error].find((e): e is ApiError => e instanceof ApiError);
  return (
    <Card className="border-warning/40">
      <CardHeader
        title={`Replace the ${repair.slot_label}`}
        description={
          affected.length
            ? `Affects ${affected.join(", ")}.`
            : "No milestone lists this skill, so only the budget changes."
        }
      />
      <div className="space-y-4 px-5 pb-5 pt-3 text-body-sm">
        {repair.status === "COMPUTING" ? (
          <SwarmIndicator label="Looking for a replacement…" />
        ) : null}
        {repair.status === "READY" ? (
          <ol className="space-y-3">
            {repair.candidates.map((c, i) => {
              const delay = c.impact.delay_days;
              return (
                <li
                  key={c.bid_id}
                  className="flex flex-col gap-3 rounded-lg border border-border p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 font-medium text-text">
                      {i === 0 ? <Badge tone="success">Best fit</Badge> : null}
                      {c.developer_name}
                      {c.is_newcomer ? <NewcomerBadge /> : null}
                    </p>
                    <p className="text-text-muted">
                      {formatMoney(c.price_paisa)} in {formatDays(c.days_needed)}; competency{" "}
                      {score(c.competency)}, teamwork {score(c.teamwork)}
                    </p>
                    <p className="text-text-muted">
                      {delay > 0
                        ? `Finishes ${formatDays(delay)} later`
                        : delay < 0
                          ? `Finishes ${formatDays(-delay)} sooner`
                          : "Same finish date"}
                      ;{" "}
                      {c.impact.budget_delta_paisa > 0
                        ? `${formatMoney(c.impact.budget_delta_paisa)} over the budget`
                        : `${formatMoney(-c.impact.budget_delta_paisa)} left in the budget`}
                    </p>
                  </div>
                  <Button
                    className="shrink-0"
                    variant={i === 0 ? "primary" : "outline"}
                    loading={choose.isPending && choose.variables.bidId === c.bid_id}
                    onClick={() => {
                      choose.mutate(
                        { proposalId: repair.id, bidId: c.bid_id },
                        {
                          onSuccess: () => {
                            toast({ tone: "success", title: "Replacement invited" });
                          },
                        },
                      );
                    }}
                  >
                    Invite
                  </Button>
                </li>
              );
            })}
          </ol>
        ) : null}
        {repair.status === "NO_CANDIDATES" ? (
          <>
            <ul className="list-disc space-y-1 pl-5 text-text">
              {repair.reasons.map((r) => (
                <li key={r.code}>
                  {r.message}
                  {r.shortfall_paisa ? ` It is ${formatMoney(r.shortfall_paisa)} short.` : ""}
                </li>
              ))}
            </ul>
            <div className="flex flex-col gap-2 sm:flex-row">
              {repair.slot_id ? (
                <Button
                  variant="outline"
                  loading={reopen.isPending}
                  onClick={() => {
                    reopen.mutate(repair.slot_id ?? "", {
                      onSuccess: () => {
                        toast({ tone: "success", title: "Place reopened for 48 hours" });
                      },
                    });
                  }}
                >
                  Reopen place (48 h)
                </Button>
              ) : null}
              {repair.reasons.some((r) => r.code === "REMAINING_BUDGET_TOO_LOW") ? (
                <RaiseBudget
                  team={team}
                  shortfall={repair.reasons.find((r) => r.shortfall_paisa)?.shortfall_paisa ?? 0}
                />
              ) : null}
            </div>
          </>
        ) : null}
        {repair.reasons.some((r) => r.code === "NEWCOMER_MINIMUM_RELAXED") &&
        repair.status === "READY" ? (
          <p className="text-text-muted">
            No newcomer bid for this role, so the newcomer minimum is relaxed for the replacement.
          </p>
        ) : null}
        {error ? (
          <p className="text-danger" role="alert">
            {error.message}
          </p>
        ) : null}
      </div>
    </Card>
  );
}

function RaiseBudget({ team, shortfall }: { team: TeamForClient; shortfall: number }) {
  const raise = useRaiseBudget(team.project_id);
  const [open, setOpen] = useState(false);
  const [taka, setTaka] = useState("");
  const value = Math.round(Number(taka) * 100);
  return (
    <Dialog
      open={open}
      onOpenChange={setOpen}
      trigger={<Button variant="outline">Raise budget</Button>}
      title="Raise the budget"
      description={`It needs at least ${formatMoney(shortfall)} more after the platform fee.`}
      footer={
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button
            variant="outline"
            onClick={() => {
              setOpen(false);
            }}
          >
            Cancel
          </Button>
          <Button
            disabled={!(value > 0)}
            loading={raise.isPending}
            onClick={() => {
              raise.mutate(
                { budgetPaisa: value, version: team.project_version },
                {
                  onSuccess: () => {
                    setOpen(false);
                    toast({ tone: "success", title: "Budget raised" });
                  },
                },
              );
            }}
          >
            Raise budget
          </Button>
        </div>
      }
    >
      <FormField
        label="New total budget (৳)"
        error={raise.error instanceof ApiError ? raise.error.message : undefined}
      >
        <Input
          inputMode="numeric"
          value={taka}
          onChange={(e) => {
            setTaka(e.target.value.replace(/[^\d]/g, ""));
          }}
        />
      </FormField>
    </Dialog>
  );
}

function Requests({ team }: { team: TeamForClient }) {
  const decide = useDecideLeadChange(team.project_id);
  const pending = team.lead_change_requests.filter((r) => r.status === "PENDING");
  if (pending.length === 0 && team.removal_requests.length === 0) return null;
  return (
    <Card>
      <CardHeader title="Requests" />
      <ul className="space-y-4 px-5 pb-5 pt-3 text-body-sm">
        {pending.map((r) => (
          <li key={r.id} className="space-y-2">
            <p className="text-text">
              <span className="font-medium">{r.requester_name}</span> asks for a lead change: “
              {r.reason}”
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                loading={decide.isPending}
                onClick={() => {
                  decide.mutate(
                    { id: r.id, verb: "approve" },
                    {
                      onSuccess: () => {
                        toast({
                          tone: "success",
                          title: "Request approved. Choose the next lead.",
                        });
                      },
                    },
                  );
                }}
              >
                Approve
              </Button>
              <ReasonDialog
                trigger={
                  <Button size="sm" variant="outline">
                    Reject
                  </Button>
                }
                title="Reject this request?"
                description="The member sees your reason."
                label="Reason"
                actionLabel="Reject request"
                onSubmit={(reason) =>
                  decide.mutateAsync({ id: r.id, verb: "reject", reason }).then(() => {
                    toast({ tone: "success", title: "Request rejected" });
                  })
                }
              />
            </div>
          </li>
        ))}
        {team.removal_requests.map((r) => (
          <li key={r.id} className="text-text">
            Removal of <span className="font-medium">{r.member_name}</span>:{" "}
            {r.status === "PENDING" ? "waiting for an admin" : r.status.toLowerCase()}
          </li>
        ))}
      </ul>
    </Card>
  );
}
