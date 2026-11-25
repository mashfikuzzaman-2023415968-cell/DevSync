/**
 * Client "Teams" `/client/teams` (D110, D134): one card per project with a team — status, how
 * many places are accepted, the lead, and what needs attention (a repair, an invitation about to
 * expire, a fully booked invitee, a lead to choose).
 */
import { AlertTriangle, Users } from "lucide-react";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Badge, Card, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { useMyTeams } from "./api";
import { ATTENTION } from "./teamText";

const STATUS: Record<string, string> = {
  PENDING: "Waiting for answers",
  ACTIVE: "Working",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
};

export default function TeamsPage() {
  const q = useMyTeams();
  return (
    <>
      <PageHeader title="Teams" description="Every team you formed, and what needs you." />
      {q.isPending ? (
        <div className="grid gap-4 md:grid-cols-2" aria-busy="true" aria-label="Loading your teams">
          <Skeleton className="h-36 w-full" />
          <Skeleton className="h-36 w-full" />
        </div>
      ) : q.isError ? (
        <Card>
          <ErrorState
            title="Your teams didn’t load"
            requestId={q.error instanceof ApiError ? q.error.requestId : null}
            onRetry={() => void q.refetch()}
          />
        </Card>
      ) : q.data.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Users />}
            title="No teams yet"
            description="When you confirm a team on a project's team formation page, it appears here."
            action={
              <Button asChild variant="outline">
                <Link to="/client/projects">See my projects</Link>
              </Button>
            }
          />
        </Card>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {q.data.map((t) => (
            <li key={t.team_id}>
              <Card className="flex h-full flex-col gap-3 p-5">
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-body font-semibold text-text">{t.project_title}</h2>
                  <Badge tone={t.team_status === "CANCELLED" ? "neutral" : "info"}>
                    {STATUS[t.team_status] ?? t.team_status}
                  </Badge>
                </div>
                <p className="text-body-sm text-text-muted">
                  {t.accepted} of {t.places} places accepted.{" "}
                  {t.lead_name ? `${t.lead_name} leads.` : "No lead yet."}
                </p>
                {t.needs_attention.length > 0 ? (
                  <ul className="space-y-1 text-body-sm text-warning">
                    {t.needs_attention.map((a) => (
                      <li key={a} className="flex items-center gap-2">
                        <AlertTriangle className="size-4" aria-hidden="true" />
                        {ATTENTION[a] ?? a}
                      </li>
                    ))}
                  </ul>
                ) : null}
                <div className="mt-auto pt-2">
                  <Button asChild variant="outline">
                    <Link to={`/client/projects/${t.project_id}/team`}>Manage team</Link>
                  </Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
