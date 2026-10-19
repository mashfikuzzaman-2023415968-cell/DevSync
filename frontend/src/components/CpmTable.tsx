/**
 * Critical-path schedule as a table (spec §9.10, §13.3 CPMTable): the "View as table"
 * alternative to the Gantt and the accessible view of the same numbers. Columns are the CPM
 * fields — earliest/latest start and finish, slack, and whether the milestone is critical.
 */
import { Badge } from "@/components/ui/Display";
import type { CpmNode } from "@/api/types";
import { cn } from "@/lib/cn";
import { formatDays } from "@/lib/format";

export function CpmTable({ nodes, className }: { nodes: CpmNode[]; className?: string | undefined }) {
  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="w-full text-body-sm">
        <caption className="sr-only">
          Critical-path schedule: earliest and latest start and finish, slack, and critical status
          for each milestone.
        </caption>
        <thead>
          <tr className="border-b border-border text-left text-text-muted">
            <th scope="col" className="py-2 pr-3 font-medium">
              Milestone
            </th>
            <th scope="col" className="py-2 px-3 text-right font-medium tabular">
              Start
            </th>
            <th scope="col" className="py-2 px-3 text-right font-medium tabular">
              Finish
            </th>
            <th scope="col" className="py-2 px-3 text-right font-medium tabular">
              Latest finish
            </th>
            <th scope="col" className="py-2 px-3 text-right font-medium tabular">
              Slack
            </th>
            <th scope="col" className="py-2 pl-3 font-medium">
              On critical path
            </th>
          </tr>
        </thead>
        <tbody>
          {nodes.map((n) => (
            <tr key={n.key} className="border-b border-border/60 last:border-0">
              <th scope="row" className="py-2 pr-3 font-normal text-text">
                {n.name}
              </th>
              <td className="py-2 px-3 text-right tabular">d{n.es}</td>
              <td className="py-2 px-3 text-right tabular">d{n.ef}</td>
              <td className="py-2 px-3 text-right tabular">d{n.lf}</td>
              <td
                className={cn(
                  "py-2 px-3 text-right tabular",
                  n.slack === 0 ? "text-text-muted" : "text-text",
                )}
              >
                {n.slack === 0 ? "—" : formatDays(n.slack)}
              </td>
              <td className="py-2 pl-3">
                {n.critical ? (
                  <Badge tone="danger">Critical</Badge>
                ) : (
                  <span className="text-text-muted">No</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
