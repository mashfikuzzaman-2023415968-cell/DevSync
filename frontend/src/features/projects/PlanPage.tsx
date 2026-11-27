/**
 * Project plan page (spec §13.9 "CPM planner / plan page", §13.5 #22). Shows the saved
 * critical-path schedule as a Gantt, a list (the phone default, D158) or a table, plus the
 * dependency graph, with summary chips for duration, number of critical milestones and the finish
 * date. Read-only: the plan is the baseline fixed at publish time; once the project has started a
 * switch shows the forecast against it (D152).
 */
import { useMemo, useState } from "react";
import { useParams } from "react-router";
import { ApiError } from "@/api/client";
import type { GraphEdge } from "@/components/DependencyGraph";
import { DependencyGraph } from "@/components/DependencyGraph";
import { dayToDate } from "@/components/Gantt";
import { ScheduleView } from "@/components/ScheduleView";
import { Switch } from "@/components/ui/Choice";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { formatDate, formatDays } from "@/lib/format";
import { useProject, useProjectPlan } from "./api";

/** Statuses in which work is under way, so the Gantt shows a "today" line. */
const STARTED = new Set(["IN_PROGRESS", "ON_HOLD", "REVIEW_WINDOW"]);
const DAY_MS = 24 * 60 * 60 * 1000;

export default function PlanPage() {
  const { id = "" } = useParams();
  const project = useProject(id);
  const plan = useProjectPlan(id);
  const [showForecast, setShowForecast] = useState(true);

  const edges = useMemo<GraphEdge[]>(
    () => (plan.data?.edges ?? []).map((e): GraphEdge => [e.predecessor, e.successor]),
    [plan.data],
  );

  if (project.isError || plan.isError) {
    const err = plan.error ?? project.error;
    const requestId = err instanceof ApiError ? err.requestId : null;
    return (
      <>
        <PageHeader title="Plan" />
        <Card>
          <ErrorState
            title="We couldn’t load this plan"
            requestId={requestId}
            onRetry={() => {
              void plan.refetch();
              void project.refetch();
            }}
          />
        </Card>
      </>
    );
  }

  if (plan.isLoading || project.isLoading) {
    return (
      <>
        <PageHeader title="Plan" />
        <Card>
          <Skeleton className="h-64 w-full" />
        </Card>
      </>
    );
  }

  const p = plan.data;
  const nodes = p?.nodes ?? [];
  const criticalCount = nodes.filter((n) => n.critical).length;
  const startDate = project.data?.start_date ?? null;
  // The last working day, matching the Gantt's "6 Nov – 14 Nov" ranges (offsets are [es, ef)).
  const finish = startDate && p ? dayToDate(startDate, Math.max(0, p.duration - 1)) : null;
  const today =
    startDate && STARTED.has(project.data?.status ?? "")
      ? Math.floor((Date.now() - new Date(startDate).getTime()) / DAY_MS)
      : null;

  return (
    <>
      <PageHeader
        title={`Plan: ${project.data?.title ?? "Project"}`}
        description="The critical path is shown in red. Milestones with slack can start later without delaying the finish."
      />

      {nodes.length === 0 ? (
        <Card>
          <EmptyState
            title="No plan yet"
            description="Add milestones and dependencies to this project to see its critical path."
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">Duration {formatDays(p?.duration ?? 0)}</Badge>
            <Badge tone="danger">
              {criticalCount} critical {criticalCount === 1 ? "milestone" : "milestones"}
            </Badge>
            {p?.baseline_version != null && (
              <Badge tone="info">Baseline v{p.baseline_version}</Badge>
            )}
            {finish && <Badge tone="neutral">Finish {formatDate(finish)}</Badge>}
            {p?.exceeds_deadline && (
              <Badge tone="warning">Runs past the {formatDays(p.deadline_days)} deadline</Badge>
            )}
          </div>

          <Card>
            <CardHeader
              title="Schedule"
              description={
                p?.forecast
                  ? `Baseline and forecast: at the current pace the work ends on day ${String(p.forecast.finish_day)}.`
                  : undefined
              }
              action={
                p?.forecast ? (
                  <Switch
                    label="Show the forecast"
                    checked={showForecast}
                    onCheckedChange={setShowForecast}
                  />
                ) : null
              }
            />
            <div className="p-5">
              <ScheduleView
                nodes={nodes}
                edges={edges}
                startDate={startDate}
                today={today}
                deadlineDays={p?.deadline_days ?? null}
                forecast={showForecast ? p?.forecast?.nodes : undefined}
              />
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Dependencies"
              description="How the milestones depend on one another. Select one to see its schedule."
            />
            <div className="p-5">
              <DependencyGraph
                nodes={nodes}
                edges={edges}
                startDate={startDate}
                budgetPaisa={project.data?.budget_paisa ?? null}
              />
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
