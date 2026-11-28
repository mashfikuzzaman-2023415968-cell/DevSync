/**
 * Milestones tab `/w/:projectId/milestones`, read-only in Phase 9 (spec §13.5 #32; D141, D152):
 * each milestone's status, share of the budget, planned and forecast dates, progress from its
 * tasks and revision count. Submission, review, escrow and the auto-approval countdown join this
 * tab in Phase 10.
 */
import { ApiError } from "@/api/client";
import { dayToDate } from "@/components/Gantt";
import { Badge, Card, Skeleton } from "@/components/ui/Display";
import { Alert, ErrorState, Progress } from "@/components/ui/Feedback";
import { useProjectPlan } from "@/features/projects/api";
import { formatDate } from "@/lib/format";
import { useWorkspace } from "./context";

const STATUS: Record<string, { label: string; tone: "neutral" | "info" | "success" | "warning" }> =
  {
    PLANNED: { label: "Planned", tone: "neutral" },
    FUNDED: { label: "Funded", tone: "neutral" },
    ACTIVE: { label: "Active", tone: "info" },
    SUBMITTED: { label: "Submitted", tone: "info" },
    CHANGES_REQUESTED: { label: "Changes requested", tone: "warning" },
    DISPUTED: { label: "Disputed", tone: "warning" },
    APPROVED: { label: "Approved", tone: "success" },
    AUTO_APPROVED: { label: "Approved", tone: "success" },
    PAID: { label: "Paid", tone: "success" },
    REFUNDED: { label: "Refunded", tone: "neutral" },
  };

export default function MilestonesTab() {
  const ws = useWorkspace();
  const plan = useProjectPlan(ws.projectId);
  if (plan.isPending) return <Skeleton className="h-64 w-full rounded-xl" aria-busy="true" />;
  if (plan.isError) {
    return (
      <Card>
        <ErrorState
          title="Milestones didn’t load"
          requestId={plan.error instanceof ApiError ? plan.error.requestId : null}
          onRetry={() => void plan.refetch()}
        />
      </Card>
    );
  }
  const p = plan.data;
  const f = p.forecast;
  const start = f?.start_date ?? null;
  const day = (d: number) => (start ? formatDate(dayToDate(start, d)) : `day ${String(d)}`);
  const byKey = new Map((f?.nodes ?? []).map((n) => [n.key, n]));
  return (
    <div className="space-y-4">
      <Alert tone="info">Submitting, reviewing and paying for milestones arrive in Phase 10.</Alert>
      <ul className="space-y-3">
        {p.nodes.map((n) => {
          const live = byKey.get(n.key);
          const status = STATUS[live?.status ?? "PLANNED"] ?? {
            label: live?.status ?? "",
            tone: "neutral",
          };
          return (
            <li key={n.key}>
              <Card className="space-y-2 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-medium text-text">{n.name}</h2>
                  <Badge tone={status.tone}>{status.label}</Badge>
                  {n.critical ? <Badge tone="danger">Critical path</Badge> : null}
                  <span className="ml-auto tabular text-body-sm text-text-muted">
                    {((n.share_bp ?? 0) / 100).toFixed(0)}% of the budget
                  </span>
                </div>
                {live ? (
                  <Progress
                    value={live.progress_pct}
                    label={`${String(live.progress_pct)}% of its tasks done`}
                    showValue
                  />
                ) : null}
                <p className="text-body-sm text-text-muted" data-volatile>
                  Planned {day(n.es)} to {day(Math.max(n.es, n.ef - 1))}
                  {live
                    ? `; forecast to ${day(Math.max(live.forecast_es, live.forecast_ef - 1))}`
                    : ""}
                  {live && live.days_late > 0 ? ` (${String(live.days_late)} days late)` : ""}.
                  {live && live.revision_count > 0
                    ? ` ${String(live.revision_count)} ${live.revision_count === 1 ? "revision" : "revisions"}.`
                    : ""}
                </p>
              </Card>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
