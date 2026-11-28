/**
 * How a project is going, at a glance (spec §13.5 #9, #13, #20): a progress ring, the next
 * deadline and the overall risk, in words as well as colour. `MyProjectRow` is a developer's
 * project (from `/me/projects`); `ClientProjectPulse` reads the client's dashboard for one
 * project in progress (it never shows money here; the Overview has the budget).
 */
import { Link } from "react-router";
import type { MyProject } from "@/api/types";
import { Badge, RiskChip } from "@/components/ui/Display";
import { RingProgress } from "@/components/ui/Feedback";
import { formatDate } from "@/lib/format";
import { HEALTH_LABEL, useDashboard } from "@/features/workspace/monitoringApi";

const STATUS_LABEL: Record<string, string> = {
  TEAM_PENDING: "Starting soon",
  IN_PROGRESS: "In progress",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
};

export function MyProjectRow({ p }: { p: MyProject }) {
  return (
    <div className="flex items-center gap-4 rounded-lg border border-border bg-surface p-4">
      {p.progress_pct !== null ? (
        <RingProgress value={p.progress_pct} label={`${p.title} progress`} size={56}>
          <span className="tabular text-caption font-semibold">{p.progress_pct}%</span>
        </RingProgress>
      ) : null}
      <div className="min-w-0 flex-1">
        <Link
          to={`/w/${p.project_id}/overview`}
          className="block break-words font-medium text-text underline-offset-2 hover:underline"
        >
          {p.title}
        </Link>
        <p className="text-caption text-text-muted">
          {p.is_lead ? `${p.role}, team lead` : p.role}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-caption">
          <Badge tone="neutral" icon={false}>
            {STATUS_LABEL[p.status] ?? p.status}
          </Badge>
          {p.next_deadline ? (
            <span className="text-text-muted">
              Next: {p.next_milestone ?? "milestone"} by {formatDate(p.next_deadline)}
            </span>
          ) : null}
          {p.overall_risk ? (
            <span className="inline-flex items-center gap-1 text-text-muted">
              Risk <RiskChip severity={p.overall_risk} />
            </span>
          ) : null}
          {p.health && p.health !== "HEALTHY" ? (
            <Badge tone={p.health === "CRITICAL" ? "danger" : "warning"}>
              {HEALTH_LABEL[p.health]}
            </Badge>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Progress, schedule impact and risk for one of the client's projects in progress. */
export function ClientProjectPulse({ projectId }: { projectId: string }) {
  const q = useDashboard(projectId);
  if (!q.data) return null;
  const d = q.data;
  const impact = d.forecast?.impact_days ?? 0;
  return (
    <div className="flex flex-wrap items-center gap-2 text-caption">
      <span className="tabular text-text">{d.progress_pct}% done</span>
      {impact > 0 ? (
        <Badge tone="warning">{`${String(impact)} ${impact === 1 ? "day" : "days"} late`}</Badge>
      ) : d.forecast ? (
        <Badge tone="success">On schedule</Badge>
      ) : null}
      {d.overall_risk ? (
        <span className="inline-flex items-center gap-1 text-text-muted">
          Risk <RiskChip severity={d.overall_risk} />
        </span>
      ) : null}
    </div>
  );
}
