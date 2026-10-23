/**
 * Dependency graph for a project's milestones (spec §9.10, §13.3 DependencyGraph).
 *
 * Custom SVG (no graph library): a left-to-right layered DAG. Each milestone sits in the layer
 * one past its latest predecessor (longest-path layering, matching the CPM topological order);
 * edges are finish-to-start. Nodes and edges on the critical path are drawn in danger (rose) so
 * the longest chain reads at a glance. Purely presentational — the caller supplies the edges.
 */
import { useId, useMemo } from "react";
import { cn } from "@/lib/cn";

export interface GraphNode {
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
  className,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  className?: string | undefined;
}) {
  const titleId = useId();
  const { placed, width, height } = useMemo(() => layout(nodes, edges), [nodes, edges]);
  const pos = new Map(placed.map((p) => [p.key, p]));

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
            className="group outline-none"
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
              className="stroke-primary opacity-0 group-focus-visible:opacity-100"
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
    </div>
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
