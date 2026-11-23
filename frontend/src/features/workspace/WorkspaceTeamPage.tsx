/**
 * Workspace shell `/w/:projectId/team` (spec §13.5 #33, §13.4; D120). The header and tab bar of
 * the project workspace with the Team tab real; the other tabs arrive in Phase 9, which fills this
 * shell. Only the project's client and its members (the API answers 404 to anyone else).
 *
 * Team tab: members with their role, lead badge, reputation (0–100) and weekly hours — never each
 * other's prices or days (D130); members can ask for a lead change, withdraw it, or leave the
 * project with a reason; the lead can decline the role.
 */
import { Crown, Users } from "lucide-react";
import { Link, useParams } from "react-router";
import { ApiError } from "@/api/client";
import type { TeamView } from "@/api/types";
import { ReasonDialog } from "@/components/ReasonDialog";
import { Button } from "@/components/ui/Button";
import { Avatar, Badge, Card, CardHeader, NewcomerBadge, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { ConfirmDialog } from "@/components/ui/Overlay";
import { toast } from "@/components/ui/toast-store";
import {
  useDecideLeadChange,
  useDeclineLead,
  useLeave,
  useRequestLeadChange,
  useTeam,
} from "@/features/team/api";
import { memberStatus, score } from "@/features/team/teamText";

const TABS = [
  "Overview",
  "Tasks",
  "Timeline",
  "Milestones",
  "Team",
  "Check-ins",
  "Files",
  "Payments",
  "Risks",
];

export default function WorkspaceTeamPage() {
  const { projectId = "" } = useParams();
  const q = useTeam(projectId);
  if (q.isPending) {
    return (
      <>
        <PageHeader title="Team" />
        <Card className="p-5" aria-busy="true" aria-label="Loading the team">
          <Skeleton className="h-32 w-full" />
        </Card>
      </>
    );
  }
  if (q.isError) {
    const err = q.error;
    return (
      <>
        <PageHeader title="Team" />
        <Card>
          {err instanceof ApiError && err.status === 404 ? (
            <EmptyState
              icon={<Users />}
              title="We couldn’t find that workspace"
              description="It may not exist, or you aren’t on this project’s team."
            />
          ) : (
            <ErrorState
              title="The team didn’t load"
              requestId={err instanceof ApiError ? err.requestId : null}
              onRetry={() => void q.refetch()}
            />
          )}
        </Card>
      </>
    );
  }
  return <Workspace team={q.data} />;
}

function Workspace({ team }: { team: TeamView }) {
  const member = team.view === "member" ? team : null;
  const me = member ? member.members.find((m) => m.id === member.my_member_id) : undefined;
  const leave = useLeave(team.project_id);
  const request = useRequestLeadChange(team.project_id);
  const decide = useDecideLeadChange(team.project_id);
  const declineLead = useDeclineLead(team.project_id);
  const myOpen = member?.lead_change_requests.find((r) => r.status === "PENDING");
  return (
    <>
      <PageHeader
        title={team.project_title}
        description={team.project_status === "IN_PROGRESS" ? "In progress." : "Waiting to start."}
        action={
          team.view === "client" ? (
            <Button asChild variant="outline">
              <Link to={`/client/projects/${team.project_id}/team`}>Manage team</Link>
            </Button>
          ) : null
        }
      />
      <nav aria-label="Workspace" className="-mx-4 mb-6 overflow-x-auto px-4">
        <ul className="flex min-w-max gap-1 border-b border-border">
          {TABS.map((tab) => (
            <li key={tab}>
              {tab === "Team" ? (
                <span
                  aria-current="page"
                  className="inline-flex min-h-11 items-center border-b-2 border-primary px-3 text-body-sm font-medium text-text"
                >
                  Team
                </span>
              ) : (
                <span
                  className="inline-flex min-h-11 items-center px-3 text-body-sm text-text-subtle"
                  title={`${tab} arrives in Phase 9`}
                >
                  {tab}
                  <span className="sr-only"> (arrives in Phase 9)</span>
                </span>
              )}
            </li>
          ))}
        </ul>
      </nav>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <Card>
          <CardHeader title="Members" />
          <ul className="divide-y divide-border px-5 pb-2">
            {team.members
              .filter((m) => m.status === "ACTIVE" || m.status === "INVITED")
              .map((m) => (
                <li key={m.id} className="flex items-start justify-between gap-3 py-4">
                  <div className="flex min-w-0 items-start gap-3">
                    <Avatar name={m.developer_name} newcomer={m.is_newcomer} />
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-2 font-medium text-text">
                        {m.developer_name}
                        {m.is_you ? <span className="text-text-muted">(you)</span> : null}
                        {m.is_lead ? (
                          <Badge tone="info" icon={false}>
                            <Crown className="size-3.5" aria-hidden="true" /> Lead
                          </Badge>
                        ) : null}
                        {m.is_newcomer ? <NewcomerBadge /> : null}
                      </p>
                      <p className="text-body-sm text-text-muted">
                        {m.slot_label}; competency {score(m.competency)}, teamwork{" "}
                        {score(m.teamwork)}, {m.hours_per_week} hours a week
                      </p>
                    </div>
                  </div>
                  <Badge tone={memberStatus(m.status).tone}>{memberStatus(m.status).label}</Badge>
                </li>
              ))}
          </ul>
        </Card>
        {me && me.status === "ACTIVE" ? (
          <Card>
            <CardHeader title="Your part" />
            <div className="flex flex-col gap-3 px-5 pb-5 pt-3 text-body-sm">
              {me.is_lead ? (
                <ConfirmDialog
                  trigger={<Button variant="outline">Decline the lead role</Button>}
                  title="Decline the lead role?"
                  description="You stay in the team; the client chooses another lead."
                  confirmLabel="Decline the lead role"
                  onConfirm={async () => {
                    await declineLead.mutateAsync(undefined);
                    toast({ tone: "success", title: "You are no longer the team lead" });
                  }}
                />
              ) : myOpen ? (
                <>
                  <p className="text-text">Your lead-change request is waiting for the client.</p>
                  <Button
                    variant="outline"
                    loading={decide.isPending}
                    onClick={() => {
                      decide.mutate({ id: myOpen.id, verb: "withdraw" });
                    }}
                  >
                    Withdraw request
                  </Button>
                </>
              ) : team.lead_member_id ? (
                <ReasonDialog
                  trigger={<Button variant="outline">Ask for a lead change</Button>}
                  title="Ask the client for a lead change?"
                  description="The client decides. Say why; the client sees it."
                  label="Reason"
                  actionLabel="Send request"
                  onSubmit={(reason) =>
                    request.mutateAsync({ reason }).then(() => {
                      toast({ tone: "success", title: "Request sent" });
                    })
                  }
                />
              ) : null}
              {member?.lead_change_requests
                .filter((r) => r.status === "REJECTED" && r.decision_reason)
                .slice(0, 1)
                .map((r) => (
                  <p key={r.id} className="text-text-muted">
                    The client didn’t change the lead: “{r.decision_reason}”
                  </p>
                ))}
              <ReasonDialog
                trigger={<Button variant="destructive">Leave project</Button>}
                title="Leave this project?"
                description="Your place opens for a replacement and the client is told. This can’t be undone."
                label="Reason"
                actionLabel="Leave project"
                destructive
                onSubmit={(reason) =>
                  leave.mutateAsync({ memberId: me.id, reason }).then(() => {
                    toast({ tone: "success", title: "You left the project" });
                  })
                }
              />
            </div>
          </Card>
        ) : null}
      </div>
    </>
  );
}
