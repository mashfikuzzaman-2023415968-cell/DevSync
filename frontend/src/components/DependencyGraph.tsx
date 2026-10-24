/**
 * Dependency graph for a project's milestones (spec §9.10, §13.3 DependencyGraph).
 *
 * Custom SVG (no graph library): a left-to-right layered DAG. Each milestone sits in the layer
 * one past its latest predecessor (longest-path layering, matching the CPM topological order);
 * edges are finish-to-start. Nodes and edges on the critical path are drawn in danger (rose) so
 * the longest chain reads at a glance. The caller supplies the edges.
 *
 * Clicking a milestone (or pressing Enter or Space on it) opens a panel with its schedule —
 * duration, earliest/latest start and finish (with dates once a start date is known), slack —
 * its share of the budget, and what it depends on and what depends on it. The panel is a side
 * sheet, and a bottom sheet on phones.
 */
import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { CpmNode } from "@/api/types";
import { Badge } from "@/components/ui/Display";
import { Sheet } from "@/components/ui/Overlay";
import { useMediaQuery } from "@/design/preferences";
import { cn } from "@/lib/cn";
import { formatDate, formatDays, formatMoney } from "@/lib/format";
import { bpOf, bpPercent } from "@/lib/money";

/** A milestone in the graph. The schedule fields and the budget share are optional: without
 * them the panel shows only the name and the dependencies. A `CpmNode` fits as it is. */
export interface GraphNode extends Partial<
  Pick<CpmNode, "es" | "ef" | "ls" | "lf" | "slack" | "share_bp">
> {
  key: string;
  name: string;
  critical: boolean;
}
export type GraphEdge = readonly [from: string, to: string];

const NODE_W = 152;
const NODE_H = 48;
/** About 20 characters of 14 px Inter fit on one line of a node. */
const LINE_CHARS = 20;
const COL_GAP = 56;
const ROW_GAP = 16;
const PAD = 16;

interface Placed extends GraphNode {
  layer: number;
  x: number;
  y: number;
}

function layout(nodes: GraphNode[], edges: GraphEdge[]) {
  const preds = new Map<string, string[]>();
  const succs = new Map<string, string[]>();
  for (const n of nodes) {
    preds.set(n.key, []);
    succs.set(n.key, []);
  }
  for (const [from, to] of edges) {
    if (preds.has(to) && succs.has(from)) {
      preds.get(to)?.push(from);
      succs.get(from)?.push(to);
    }
  }
  // Longest-path layering via repeated relaxation (graph is acyclic by the time it renders).
  const layer = new Map<string, number>(nodes.map((n) => [n.key, 0]));
  for (let pass = 0; pass < nodes.length; pass += 1) {
    let changed = false;
    for (const n of nodes) {
      const want = preds.get(n.key)?.reduce((m, p) => Math.max(m, (layer.get(p) ?? 0) + 1), 0) ?? 0;
      if (want !== layer.get(n.key)) {
        layer.set(n.key, want);
        changed = true;
      }
    }
    if (!changed) break;
  }

  const byLayer = new Map<number, GraphNode[]>();
  for (const n of nodes) {
    const l = layer.get(n.key) ?? 0;
    const group = byLayer.get(l) ?? [];
    group.push(n);
    byLayer.set(l, group);
  }
  const placed: Placed[] = [];
  let maxRows = 0;
  for (const [l, group] of [...byLayer.entries()].sort((a, b) => a[0] - b[0])) {
    maxRows = Math.max(maxRows, group.length);
    group.forEach((n, row) => {
      placed.push({
        ...n,
        layer: l,
        x: PAD + l * (NODE_W + COL_GAP),
        y: PAD + row * (NODE_H + ROW_GAP),
      });
    });
  }
  const layers = byLayer.size;
  const width = PAD * 2 + layers * NODE_W + Math.max(0, layers - 1) * COL_GAP;
  const height = PAD * 2 + maxRows * NODE_H + Math.max(0, maxRows - 1) * ROW_GAP;
  return { placed, width, height };
}

export function DependencyGraph({
  nodes,
  edges,
  startDate = null,
  budgetPaisa = null,
  className,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Project start date (ISO), so the panel can show calendar dates. */
  startDate?: string | null;
  /** Project budget in paisa, so the panel can show the share as an amount. */
  budgetPaisa?: number | null;
  className?: string | undefined;
}) {
  const titleId = useId();
  const hintId = useId();
  const { placed, width, height } = useMemo(() => layout(nodes, edges), [nodes, edges]);
  const pos = new Map(placed.map((p) => [p.key, p]));
  const [selected, setSelected] = useState<string | null>(null);
  // The node that opened the panel gets focus back when it closes.
  const opener = useRef<SVGGElement | null>(null);
  const wide = useMediaQuery("(min-width: 768px)");
  const selectedNode = selected ? nodes.find((n) => n.key === selected) : undefined;
  const open = (key: string) => (e: KeyboardEvent<SVGGElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault(); // Space would scroll the page
      opener.current = e.currentTarget;
      setSelected(key);
    }
  };

  return (
    <div className={cn("overflow-x-auto", className)}>
      <svg
        role="img"
        aria-labelledby={titleId}
        width={width}
        height={height}
        viewBox={`0 0 ${String(width)} ${String(height)}`}
        className="min-w-full"
      >
        <title id={titleId}>
          Dependency graph: {nodes.length} milestones; the critical path is shown in red.
        </title>
        <desc id={hintId}>Press Enter to see this milestone’s schedule and dependencies.</desc>
        <g fill="none" strokeWidth="1.5">
          {edges.map(([from, to], i) => {
            const a = pos.get(from);
            const b = pos.get(to);
            if (!a || !b) return null;
            const x1 = a.x + NODE_W;
            const y1 = a.y + NODE_H / 2;
            const x2 = b.x;
            const y2 = b.y + NODE_H / 2;
            const mx = (x1 + x2) / 2;
            const critical = a.critical && b.critical;
            return (
              <path
                key={`e${String(i)}`}
                d={`M${String(x1)},${String(y1)} C${String(mx)},${String(y1)} ${String(mx)},${String(y2)} ${String(x2)},${String(y2)}`}
                className={critical ? "stroke-danger" : "stroke-border"}
              />
            );
          })}
        </g>
        {/* Each milestone is a focus stop, so keyboard users can also reach (and scroll to) the
            parts of a wide graph that sit off screen. */}
        {placed.map((n) => (
          <g
            key={n.key}
            tabIndex={0}
            role="group"
            aria-label={n.critical ? `${n.name}, on the critical path` : n.name}
            aria-describedby={hintId}
            onClick={(e) => {
              opener.current = e.currentTarget;
              setSelected(n.key);
            }}
            onKeyDown={open(n.key)}
            className="group cursor-pointer outline-none"
          >
            <rect
              x={n.x}
              y={n.y}
              width={NODE_W}
              height={NODE_H}
              rx="8"
              className={cn("fill-surface", n.critical ? "stroke-danger" : "stroke-border")}
              strokeWidth={n.critical ? "2" : "1"}
            />
            <rect
              x={n.x - 3}
              y={n.y - 3}
              width={NODE_W + 6}
              height={NODE_H + 6}
              rx="10"
              fill="none"
              strokeWidth="2"
              className={cn(
                "stroke-primary group-focus-visible:opacity-100",
                selected === n.key ? "opacity-100" : "opacity-0",
              )}
            />
            <title>{n.name}</title>
            <text
              x={n.x + NODE_W / 2}
              y={n.y + NODE_H / 2 + 4}
              textAnchor="middle"
              className={cn("text-body-sm", n.critical ? "fill-danger" : "fill-text")}
            >
              {nameLines(n.name).map((line, i, all) => (
                <tspan
                  key={String(i)}
                  x={n.x + NODE_W / 2}
                  dy={i === 0 ? (all.length - 1) * -8 : 16}
                >
                  {line}
                </tspan>
              ))}
            </text>
          </g>
        ))}
      </svg>
      <Sheet
        open={selectedNode !== undefined}
        onOpenChange={(o) => {
          if (!o) setSelected(null);
        }}
        side={wide ? "right" : "bottom"}
        onCloseAutoFocus={(e) => {
          if (opener.current?.isConnected) {
            e.preventDefault();
            opener.current.focus();
          }
        }}
        title={selectedNode?.name ?? "Milestone"}
        description={selectedNode ? summary(selectedNode) : undefined}
      >
        {selectedNode ? (
          <MilestonePanel
            node={selectedNode}
            nodes={nodes}
            edges={edges}
            startDate={startDate}
            budgetPaisa={budgetPaisa}
          />
        ) : null}
      </Sheet>
    </div>
  );
}

function summary(node: GraphNode): string {
  if (node.critical) return "On the critical path, so any delay moves the finish date.";
  if (node.slack !== undefined) {
    return `Can slip ${formatDays(node.slack)} without delaying the finish.`;
  }
  return "Not on the critical path.";
}

/** Day `day` of the plan as text, with its calendar date when the start date is known. */
function dayText(day: number, startDate: string | null): string {
  if (!startDate) return `Day ${String(day)}`;
  const d = new Date(startDate);
  d.setUTCDate(d.getUTCDate() + day);
  return `Day ${String(day)} (${formatDate(d)})`;
}

function MilestonePanel({
  node,
  nodes,
  edges,
  startDate,
  budgetPaisa,
}: {
  node: GraphNode;
  nodes: GraphNode[];
  edges: GraphEdge[];
  startDate: string | null;
  budgetPaisa: number | null;
}) {
  const names = new Map(nodes.map((n) => [n.key, n.name]));
  const listed = (keys: string[]) =>
    keys.map((k) => names.get(k)).filter((n): n is string => Boolean(n));
  const after = listed(edges.filter(([, to]) => to === node.key).map(([from]) => from));
  const before = listed(edges.filter(([from]) => from === node.key).map(([, to]) => to));
  const { es, ef, ls, lf, slack } = node;
  const share = node.share_bp ?? null;
  const shareText =
    share === null
      ? null
      : budgetPaisa && budgetPaisa > 0
        ? `${bpPercent(share)} (${formatMoney(bpOf(budgetPaisa, share))})`
        : bpPercent(share);
  // Finishes are the last working day, like the Gantt's ranges (offsets are [start, finish)).
  const lastDay = (finish: number, start: number) => Math.max(start, finish - 1);

  return (
    <div className="flex flex-col gap-5 text-body-sm">
      <div>
        {node.critical ? (
          <Badge tone="danger">Critical path</Badge>
        ) : (
          <Badge tone="info">Has slack</Badge>
        )}
      </div>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2">
        {es !== undefined && ef !== undefined && (
          <>
            <Row label="Duration" value={formatDays(ef - es)} />
            <Row label="Earliest start" value={dayText(es, startDate)} />
            <Row label="Earliest finish" value={dayText(lastDay(ef, es), startDate)} />
          </>
        )}
        {ls !== undefined && lf !== undefined && (
          <>
            <Row label="Latest start" value={dayText(ls, startDate)} />
            <Row label="Latest finish" value={dayText(lastDay(lf, ls), startDate)} />
          </>
        )}
        {slack !== undefined && (
          <Row label="Slack" value={slack === 0 ? "None" : formatDays(slack)} />
        )}
        {shareText !== null && <Row label="Share of budget" value={shareText} />}
      </dl>
      <section>
        <h3 className="mb-1 font-medium text-text">Depends on</h3>
        {after.length > 0 ? (
          <ul className="list-inside list-disc text-text">
            {after.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        ) : (
          <p className="text-text-muted">Nothing, so it can start right away.</p>
        )}
      </section>
      <section>
        <h3 className="mb-1 font-medium text-text">Needed by</h3>
        {before.length > 0 ? (
          <ul className="list-inside list-disc text-text">
            {before.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        ) : (
          <p className="text-text-muted">Nothing waits for it, so it ends the plan.</p>
        )}
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-text-muted">{label}</dt>
      <dd className="font-medium tabular text-text">{value}</dd>
    </>
  );
}

/** A name on at most two lines, split at spaces; only text beyond two lines is elided. */
export function nameLines(name: string, max = LINE_CHARS): string[] {
  const lines: string[] = [];
  let current = "";
  for (const word of name.trim().split(/\s+/)) {
    for (let rest = word; rest;) {
      const room = current ? max - current.length - 1 : max;
      if (rest.length <= room) {
        current = current ? `${current} ${rest}` : rest;
        rest = "";
      } else if (current) {
        lines.push(current);
        current = "";
      } else {
        lines.push(rest.slice(0, max));
        rest = rest.slice(max);
      }
    }
  }
  if (current) lines.push(current);
  if (lines.length <= 2) return lines;
  const second = lines[1] ?? "";
  return [lines[0] ?? "", `${second.slice(0, max - 1).trimEnd()}…`];
}
