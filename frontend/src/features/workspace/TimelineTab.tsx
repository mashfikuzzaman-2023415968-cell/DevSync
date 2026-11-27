/**
 * Timeline tab `/w/:projectId/timeline` (spec §13.5 #31; D152, D158): the baseline plan with the
 * forecast under it, the critical path, a today line and the deadline; on phones a list first.
 * The forecast comes from the same evaluation the Overview shows, so they never disagree.
 */
import { ApiError } from "@/api/client";
import { ScheduleView } from "@/components/ScheduleView";
import { Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { ErrorState } from "@/components/ui/Feedback";
import { useProjectPlan } from "@/features/projects/api";
import { useWorkspace } from "./context";

export default function TimelineTab() {
  const ws = useWorkspace();
  const plan = useProjectPlan(ws.projectId);
  if (plan.isPending) {
    return <Skeleton className="h-80 w-full rounded-xl" aria-busy="true" />;
  }
  if (plan.isError) {
    return (
      <Card>
        <ErrorState
          title="The timeline didn’t load"
          requestId={plan.error instanceof ApiError ? plan.error.requestId : null}
          onRetry={() => void plan.refetch()}
        />
      </Card>
    );
  }
  const p = plan.data;
  const f = p.forecast;
  const late = f ? f.impact_days : 0;
  return (
    <Card>
      <CardHeader
        title="Baseline and forecast"
        description={
          f
            ? late > 0
              ? `At the current pace the work ends on day ${String(f.finish_day)}, ${String(late)} ${late === 1 ? "day" : "days"} after the ${String(p.duration)}-day plan.`
              : `At the current pace the work ends on day ${String(f.finish_day)}, within the ${String(p.duration)}-day plan.`
            : `The ${String(p.duration)}-day plan.`
        }
      />
      <div className="px-5 pb-5">
        <ScheduleView
          nodes={p.nodes}
          edges={p.edges.map((e) => [e.predecessor, e.successor] as const)}
          startDate={f?.start_date ?? null}
          today={f?.today ?? null}
          deadlineDays={p.deadline_days}
          forecast={f?.nodes}
        />
      </div>
    </Card>
  );
}
