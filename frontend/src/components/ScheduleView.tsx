/**
 * Baseline vs forecast schedule, shared by the plan page (#22) and the workspace Timeline (#31)
 * (spec §13.14, D152, D158). On wide screens the Gantt; on phones a list of cards (dates, slack,
 * critical badge, forecast) by default, with "Show timeline" for the scrollable Gantt. "View as
 * table" is always there (D95: every chart has a table).
 */
import { useState } from "react";
import type { CpmNode, ForecastNode } from "@/api/types";
import { CpmTable } from "@/components/CpmTable";
import { dayToDate, Gantt, type ForecastBar, type GanttEdge } from "@/components/Gantt";
import { Badge, Card } from "@/components/ui/Display";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { formatDate, formatDays } from "@/lib/format";

type View = "gantt" | "list" | "table";

function phone(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(max-width: 767px)").matches
    : false;
}

export function ScheduleView({
  nodes,
  edges,
  startDate,
  today,
  deadlineDays,
  forecast,
}: {
  nodes: CpmNode[];
  edges: readonly GanttEdge[];
  startDate: string | null;
  today: number | null;
  deadlineDays: number | null;
  forecast?: ForecastNode[] | undefined;
}) {
  const [view, setView] = useState<View>(() => (phone() ? "list" : "gantt"));
  const bars = forecast
    ? new Map<string, ForecastBar>(
        forecast.map((f) => [f.key, { es: f.forecast_es, ef: f.forecast_ef }]),
      )
    : undefined;
  const byKey = new Map((forecast ?? []).map((f) => [f.key, f]));
  const date = (day: number) =>
    startDate ? formatDate(dayToDate(startDate, day)) : `day ${String(day)}`;
  return (
    <div className="space-y-4">
      <SegmentedControl<View>
        label="Schedule view"
        size="sm"
        value={view}
        onChange={setView}
        segments={[
          { value: "list", label: "List" },
          { value: "gantt", label: "Gantt" },
          { value: "table", label: "Table" },
        ]}
      />
      {view === "gantt" ? (
        <Gantt
          nodes={nodes}
          edges={edges}
          startDate={startDate}
          today={today}
          deadlineDays={deadlineDays}
          forecast={bars}
        />
      ) : view === "table" ? (
        <CpmTable nodes={nodes} />
      ) : (
        <ul className="space-y-3">
          {nodes.map((n) => {
            const f = byKey.get(n.key);
            const late = f ? f.forecast_ef - n.ef : 0;
            return (
              <li key={n.key}>
                <Card className="space-y-1 p-4 text-body-sm">
                  <p className="flex flex-wrap items-center gap-2 font-medium text-text">
                    {n.name}
                    {n.critical ? <Badge tone="danger">Critical path</Badge> : null}
                  </p>
                  <p className="text-text-muted">
                    Planned {date(n.es)} to {date(Math.max(n.es, n.ef - 1))}
                    {n.critical ? "." : `; can slip ${formatDays(n.slack)}.`}
                  </p>
                  {f ? (
                    <p
                      className={late > 0 ? "font-medium text-warning" : "text-success"}
                      data-volatile
                    >
                      Forecast to finish {date(Math.max(f.forecast_es, f.forecast_ef - 1))}
                      {late > 0 ? `, ${formatDays(late)} late.` : ", on plan."}
                    </p>
                  ) : null}
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
