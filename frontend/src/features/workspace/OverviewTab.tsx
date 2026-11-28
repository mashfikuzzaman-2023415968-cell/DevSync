/**
 * Overview tab `/w/:projectId/overview` (spec §13.5 #29, §13.9 "Workspace overview (Demo 2)";
 * D151, D152). Progress ring, schedule (done vs planned by today), forecast finish with its impact,
 * team health and overall risk, the top three risks with their actions, the next milestone, the
 * budget donut (client and admins only) and recent activity. Every computed number has one plain
 * sentence of why; "updated" says when the risks were last evaluated.
 */
import { Activity, CalendarClock, Gauge, HeartPulse } from "lucide-react";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import type { Dashboard } from "@/api/types";
import { BudgetDonut } from "@/components/BudgetDonut";
import { RiskList } from "@/components/RiskList";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { ErrorState, Progress, RingProgress } from "@/components/ui/Feedback";
import { formatDate, formatDateTime, formatRelative } from "@/lib/format";
import { useWorkspace } from "./context";
import { HEALTH_LABEL, useActivity, useDashboard } from "./monitoringApi";
import { actionTarget } from "./RisksTab";

const HEALTH_TONE = { HEALTHY: "success", AT_RISK: "warning", CRITICAL: "danger" } as const;

/** "Finishes on 8 Dec 2026, 2 days after the plan." */
export function forecastSentence(d: Dashboard): string {
  const f = d.forecast;
  if (!f) return "No forecast yet.";
  const when = f.finish_date ? `on ${formatDate(f.finish_date)}` : `on day ${String(f.finish_day)}`;
  if (f.impact_days > 0) {
    return `Forecast to finish ${when}, ${String(f.impact_days)} ${f.impact_days === 1 ? "day" : "days"} after the plan.`;
  }
  if (f.impact_days < 0) return `Forecast to finish ${when}, ahead of the plan.`;
  return `Forecast to finish ${when}, on plan.`;
}

export default function OverviewTab() {
  const ws = useWorkspace();
  const q = useDashboard(ws.projectId);
  const feed = useActivity(ws.projectId, 8);
  if (q.isPending) {
    return (
      <div className="grid gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]" aria-busy="true"
           aria-label="Loading the overview">
        <Skeleton className="h-72 w-full rounded-xl" />
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    ); // prettier-ignore
  }
  if (q.isError) {
    return (
      <Card>
        <ErrorState
          title="The overview didn’t load"
          requestId={q.error instanceof ApiError ? q.error.requestId : null}
          onRetry={() => void q.refetch()}
        />
      </Card>
    );
  }
  const d = q.data;
  const behind = d.schedule.actual_pct < d.schedule.planned_pct;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
      <div className="space-y-6">
        <Card>
          <CardHeader
            title="Progress"
            description={
              d.evaluated_at ? (
                <span data-volatile>Updated {formatRelative(d.evaluated_at)}</span>
              ) : (
                "Computed now; risks are checked after each change."
              )
            }
          />
          <div className="grid gap-6 px-5 pb-5 sm:grid-cols-[auto_minmax(0,1fr)]">
            <RingProgress value={d.progress_pct} label="Work done" size={120}>
              <span className="tabular text-h4 font-semibold">{d.progress_pct}%</span>
            </RingProgress>
            <dl className="space-y-4 text-body-sm">
              <div>
                <dt className="flex items-center gap-2 font-medium text-text">
                  <Gauge className="size-4" aria-hidden="true" /> Schedule
                </dt>
                <dd className="mt-1 space-y-1 text-text-muted">
                  <Progress value={d.schedule.actual_pct} label="Done" />
                  <p>
                    {d.schedule.actual_pct}% done; {d.schedule.planned_pct}% was planned by today
                    {behind ? ", so the team is behind." : "."}
                  </p>
                </dd>
              </div>
              <div>
                <dt className="flex items-center gap-2 font-medium text-text">
                  <CalendarClock className="size-4" aria-hidden="true" /> Forecast
                </dt>
                <dd className="mt-1 flex flex-wrap items-center gap-2 text-text-muted">
                  <span data-volatile>{forecastSentence(d)}</span>
                  {d.forecast && d.forecast.impact_days > 0 ? (
                    <Badge tone="warning">+{d.forecast.impact_days} days</Badge>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt className="flex items-center gap-2 font-medium text-text">
                  <HeartPulse className="size-4" aria-hidden="true" /> Team health
                </dt>
                <dd className="mt-1 flex flex-wrap items-center gap-2 text-text-muted">
                  <Badge tone={HEALTH_TONE[d.health]}>{HEALTH_LABEL[d.health]}</Badge>
                  <span>
                    {d.overall_risk
                      ? `The highest open risk is ${d.overall_risk.toLowerCase()}.`
                      : "No open risks."}
                  </span>
                </dd>
              </div>
            </dl>
          </div>
        </Card>
        <Card>
          <CardHeader
            title="Top risks"
            action={
              <Button asChild size="sm" variant="ghost">
                <Link to="../risks" relative="path">
                  All risks
                </Link>
              </Button>
            }
          />
          <div className="px-5 pb-5">
            <RiskList risks={d.top_risks} target={actionTarget(ws)} compact />
          </div>
        </Card>
      </div>
      <div className="space-y-6">
        {d.next_milestone ? (
          <Card>
            <CardHeader title="Next milestone" />
            <div className="space-y-2 px-5 pb-5 text-body-sm">
              <p className="font-medium text-text">{d.next_milestone.name}</p>
              <Progress
                value={d.next_milestone.progress_pct}
                label={`${String(d.next_milestone.progress_pct)}% done`}
              />
              <p className="text-text-muted" data-volatile>
                {d.next_milestone.forecast_finish_date
                  ? `Forecast ${formatDate(d.next_milestone.forecast_finish_date)}`
                  : "Not forecast yet"}
                {d.next_milestone.planned_finish_date
                  ? `; planned ${formatDate(d.next_milestone.planned_finish_date)}.`
                  : "."}
              </p>
            </div>
          </Card>
        ) : null}
        {"budget" in d ? (
          <Card>
            <CardHeader title="Budget" />
            <div className="px-5 pb-5">
              <BudgetDonut budget={d.budget} />
            </div>
          </Card>
        ) : null}
        <Card>
          <CardHeader title="Recent activity" />
          <ul className="space-y-2 px-5 pb-5 text-body-sm">
            {feed.isPending ? (
              <li>
                <Skeleton className="h-12 w-full" />
              </li>
            ) : (feed.data?.pages[0]?.items ?? []).length === 0 ? (
              <li className="text-text-muted">Nothing yet.</li>
            ) : (
              (feed.data?.pages[0]?.items ?? []).map((a) => (
                <li key={a.id} className="flex items-start gap-2">
                  <Activity
                    className="mt-0.5 size-4 shrink-0 text-text-subtle"
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1 text-text">{a.summary}</span>
                  <time
                    className="shrink-0 text-caption text-text-muted"
                    dateTime={a.at}
                    title={formatDateTime(a.at)}
                    data-volatile
                  >
                    {formatRelative(a.at)}
                  </time>
                </li>
              ))
            )}
          </ul>
        </Card>
      </div>
    </div>
  );
}
