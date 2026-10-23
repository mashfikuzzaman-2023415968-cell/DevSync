/**
 * Milestones step of the create-project wizard (spec §13.9 "Create project — milestones step").
 *
 * The client lists milestones (name, days, budget share, skills) and picks which must finish
 * before each one. A debounced call to POST /projects/{id}/plan/preview runs the pure CPM
 * algorithm server-side and returns the schedule, which is drawn as a Gantt and a dependency
 * graph with the critical path in rose. Nothing is persisted here — the parent saves on
 * "Continue"; this step only edits local rows and shows what the plan would look like.
 */
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { CpmPreview, PreviewMilestone, Skill } from "@/api/types";
import { CpmTable } from "@/components/CpmTable";
import { DependencyGraph, type GraphEdge } from "@/components/DependencyGraph";
import { Gantt } from "@/components/Gantt";
import { Button, IconButton } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Display";
import { Alert, Progress } from "@/components/ui/Feedback";
import { Field, FormField } from "@/components/ui/Field";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { cn } from "@/lib/cn";
import { formatDays } from "@/lib/format";
import { usePlanPreview } from "./api";
import { newKey, SHARE_TOTAL_BP, type MilestoneRow } from "./schemas";
import { TagPicker } from "./TagPicker";

type PreviewView = "gantt" | "graph" | "table";

const PREVIEW_DELAY_MS = 500;

export function MilestonesStep({
  projectId,
  milestones,
  onChange,
  skills,
  teamSize,
  slotCount,
  deadlineDays = null,
  startDate = null,
  onResult,
}: {
  projectId: string;
  milestones: MilestoneRow[];
  onChange: (next: MilestoneRow[]) => void;
  skills: Skill[];
  teamSize: number;
  slotCount: number;
  deadlineDays?: number | null;
  /** The project's start date (ISO), when chosen, so the preview shows real dates. */
  startDate?: string | null;
  onResult?: (result: CpmPreview | null) => void;
}) {
  const preview = usePlanPreview(projectId);
  const [view, setView] = useState<PreviewView>("gantt");
  const [result, setResult] = useState<CpmPreview | null>(null);

  const totalBp = milestones.reduce((s, m) => s + (m.share_bp || 0), 0);
  const ready =
    milestones.length > 0 && milestones.every((m) => m.name.trim() && m.duration_days > 0);

  // Debounced preview: the request key changes only when the plan changes.
  const planKey = JSON.stringify(
    milestones.map((m) => [m.key, m.name, m.duration_days, m.share_bp, m.predecessor_keys]),
  );
  const run = preview.mutate;
  useEffect(() => {
    if (!ready) {
      setResult(null);
      onResult?.(null);
      return undefined;
    }
    const body = {
      milestones: milestones.map((m): PreviewMilestone => ({
        key: m.key,
        name: m.name,
        duration_days: m.duration_days,
        share_bp: m.share_bp,
        predecessor_keys: m.predecessor_keys,
      })),
      team_size: teamSize,
      slot_count: slotCount,
    };
    const timer = window.setTimeout(() => {
      run(body, {
        onSuccess: (r) => {
          setResult(r);
          onResult?.(r);
        },
      });
    }, PREVIEW_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
    };
    // planKey stands in for the milestone contents.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planKey, teamSize, slotCount, ready, run]);

  const edges = useMemo<GraphEdge[]>(
    () =>
      milestones.flatMap((m) =>
        m.predecessor_keys
          .filter((p) => milestones.some((x) => x.key === p))
          .map((p): GraphEdge => [p, m.key]),
      ),
    [milestones],
  );

  function update(key: string, patch: Partial<MilestoneRow>) {
    onChange(milestones.map((m) => (m.key === key ? { ...m, ...patch } : m)));
  }
  function remove(key: string) {
    onChange(
      milestones
        .filter((m) => m.key !== key)
        .map((m) => ({ ...m, predecessor_keys: m.predecessor_keys.filter((p) => p !== key) })),
    );
  }
  function add() {
    onChange([
      ...milestones,
      {
        key: newKey(),
        name: "",
        duration_days: 3,
        share_bp: 0,
        skill_ids: [],
        predecessor_keys: [],
      },
    ]);
  }

  const skillOptions = skills.map((s) => ({ value: s.id, label: s.name }));

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <Card>
        <CardHeader
          title="Milestones"
          description="Split the work into milestones. Shares must add up to 100%."
        />
        <ul className="mt-4 flex flex-col gap-4">
          {milestones.map((m, i) => {
            // Any other milestone may come first. A loop is allowed here on purpose so the plan
            // preview can show it and the client can fix it (Demo 1: "a circular dependency is
            // rejected"); "Continue" stays disabled and the server rejects it too.
            const others = milestones.filter((x) => x.key !== m.key);
            return (
              <li key={m.key} className="rounded-lg border border-border p-4">
                <div className="flex items-start gap-3">
                  <span className="mt-2.5 text-caption font-semibold tabular text-text-muted">
                    {i + 1}
                  </span>
                  <div className="grid flex-1 grid-cols-[minmax(0,1fr)] gap-3 sm:grid-cols-6">
                    <div className="sm:col-span-4">
                      <Field
                        label="Name"
                        value={m.name}
                        onChange={(e) => {
                          update(m.key, { name: e.target.value });
                        }}
                        placeholder="e.g. Database schema"
                        maxLength={160}
                      />
                    </div>
                    <div className="sm:col-span-1">
                      <Field
                        label="Days"
                        type="number"
                        inputMode="numeric"
                        min={1}
                        max={365}
                        value={m.duration_days}
                        onChange={(e) => {
                          update(m.key, { duration_days: Number(e.target.value) });
                        }}
                      />
                    </div>
                    <div className="sm:col-span-1">
                      <Field
                        label="Share %"
                        type="number"
                        inputMode="numeric"
                        min={0}
                        max={100}
                        value={bpToPct(m.share_bp)}
                        onChange={(e) => {
                          update(m.key, { share_bp: pctToBp(Number(e.target.value)) });
                        }}
                      />
                    </div>
                    <div className="sm:col-span-3">
                      <FormField label="Skills">
                        {(a11y) => (
                          <TagPicker
                            id={a11y.id}
                            aria-describedby={a11y["aria-describedby"]}
                            options={skillOptions}
                            value={m.skill_ids}
                            onChange={(v) => {
                              update(m.key, { skill_ids: v });
                            }}
                            empty="Add skills in the earlier step."
                          />
                        )}
                      </FormField>
                    </div>
                    <div className="sm:col-span-3">
                      <FormField
                        label="Must finish after"
                        hint={others.length ? undefined : "Add another milestone to link them."}
                      >
                        {(a11y) => (
                          <TagPicker
                            id={a11y.id}
                            aria-describedby={a11y["aria-describedby"]}
                            options={others.map((p) => ({
                              value: p.key,
                              label: p.name || "Untitled",
                            }))}
                            value={m.predecessor_keys}
                            onChange={(v) => {
                              update(m.key, { predecessor_keys: v });
                            }}
                            empty="Add another milestone first."
                          />
                        )}
                      </FormField>
                    </div>
                  </div>
                  <IconButton
                    onClick={() => {
                      remove(m.key);
                    }}
                    aria-label={`Remove ${m.name || "milestone"}`}
                    className="mt-5"
                  >
                    <Trash2 aria-hidden="true" />
                  </IconButton>
                </div>
              </li>
            );
          })}
        </ul>
        <div className="mt-4 flex items-center justify-between gap-4">
          <Button variant="outline" onClick={add} disabled={milestones.length >= 300}>
            <Plus aria-hidden="true" />
            Add milestone
          </Button>
          <ShareMeter totalBp={totalBp} />
        </div>
      </Card>

      <Card>
        <div className="flex items-center justify-between gap-3">
          <CardHeader
            title="Plan preview"
            description="Runs the critical-path method as you edit."
          />
          <SegmentedControl<PreviewView>
            label="Plan view"
            size="sm"
            value={view}
            onChange={setView}
            segments={[
              { value: "gantt", label: "Gantt" },
              { value: "graph", label: "Graph" },
              { value: "table", label: "Table" },
            ]}
          />
        </div>
        <div className="mt-4">
          <PreviewBody
            ready={ready}
            result={result}
            edges={edges}
            view={view}
            deadlineDays={deadlineDays}
            startDate={startDate}
          />
        </div>
      </Card>
    </div>
  );
}

function PreviewBody({
  ready,
  result,
  edges,
  view,
  deadlineDays,
  startDate,
}: {
  ready: boolean;
  result: CpmPreview | null;
  edges: GraphEdge[];
  view: PreviewView;
  deadlineDays: number | null;
  startDate: string | null;
}) {
  if (!ready || !result) {
    return (
      <p className="py-8 text-center text-body-sm text-text-muted">
        Add a milestone with a name and a duration to see the timeline.
      </p>
    );
  }
  if (result.cycle && result.cycle.length > 0) {
    return (
      <Alert tone="danger" title="These milestones depend on each other in a loop">
        Remove a dependency in the chain {result.cycle.join(" → ")} so the work can be scheduled.
      </Alert>
    );
  }
  const graphNodes = result.nodes.map((n) => ({ key: n.key, name: n.name, critical: n.critical }));
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2 text-body-sm">
        <Chip>Duration {formatDays(result.duration)}</Chip>
        <Chip>{result.nodes.filter((n) => n.critical).length} critical milestones</Chip>
        <Chip tone={result.total_share_bp === SHARE_TOTAL_BP ? "ok" : "warn"}>
          Shares {bpToPct(result.total_share_bp)}%
        </Chip>
      </div>
      {result.warnings.map((w) => (
        <Alert key={w} tone="warning" title="Heads up">
          {w}
        </Alert>
      ))}
      {view === "gantt" && (
        <Gantt
          nodes={result.nodes}
          edges={edges}
          startDate={startDate}
          deadlineDays={deadlineDays}
        />
      )}
      {view === "graph" && <DependencyGraph nodes={graphNodes} edges={edges} />}
      {view === "table" && <CpmTable nodes={result.nodes} />}
    </div>
  );
}

function ShareMeter({ totalBp }: { totalBp: number }) {
  const pct = bpToPct(totalBp);
  const ok = totalBp === SHARE_TOTAL_BP;
  return (
    <div className="min-w-40">
      <p
        className={cn(
          "mb-1 text-right text-body-sm font-medium tabular",
          ok ? "text-success" : "text-text-muted",
        )}
      >
        Share total {pct}%{ok ? " ✓" : ""}
      </p>
      <Progress
        value={Math.min(totalBp, SHARE_TOTAL_BP)}
        max={SHARE_TOTAL_BP}
        tone={ok ? "success" : "primary"}
        label={`Milestone budget shares total ${String(pct)} percent`}
        className="w-40"
      />
    </div>
  );
}

function Chip({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "ok" | "warn";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-caption font-medium",
        tone === "ok" && "bg-success-bg text-success",
        tone === "warn" && "bg-warning-bg text-warning",
        tone === "neutral" && "bg-surface-2 text-text",
      )}
    >
      {children}
    </span>
  );
}

const bpToPct = (bp: number): number => Math.round((bp / 100) * 10) / 10;
const pctToBp = (pct: number): number => Math.round(pct * 100);
