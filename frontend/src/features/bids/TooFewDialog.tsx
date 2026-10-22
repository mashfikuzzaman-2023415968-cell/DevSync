/**
 * The too-few-bids actions (spec §9.19, §13.5 #23): extend bidding, lower the minimum
 * standards, raise the budget, reduce the team, or cancel. Every change that touches Algorithm 1
 * shows its effect before the client confirms ("Lowering minimum performance to 40 makes 2 more
 * bids eligible"); the server re-checks every rule (floors, raise-only budget, reduce-only team,
 * D54) and tells each bidder their eligibility may have changed.
 */
import { useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import type { ClientBids, Project, TermsChange, TermsPreview } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Field, FormField, Textarea } from "@/components/ui/Field";
import { Alert } from "@/components/ui/Feedback";
import { Tabs } from "@/components/ui/Disclosure";
import { Dialog } from "@/components/ui/Overlay";
import { Select } from "@/components/ui/Select";
import { Slider } from "@/components/ui/Slider";
import { toast } from "@/components/ui/toast-store";
import { formatDate, formatMoney } from "@/lib/format";
import { useCancelProject, useExtendBidding } from "@/features/projects/api";
import { useChangeTerms, useTermsPreview } from "./api";

/** Wait for the client to stop adjusting before asking the server for a preview. */
const PREVIEW_DEBOUNCE_MS = 350;

type Action = "extend" | "standards" | "budget" | "team" | "cancel";

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "That didn’t work. Try again.";
}

/** Debounced server preview of a terms change; null change → no preview. */
function useEffectPreview(projectId: string, change: TermsChange | null) {
  const preview = useTermsPreview(projectId);
  const key = change ? JSON.stringify(change) : "";
  const { mutate, reset } = preview;
  useEffect(() => {
    if (!key) {
      reset();
      return undefined;
    }
    const timer = window.setTimeout(() => {
      mutate(JSON.parse(key) as TermsChange);
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [key, mutate, reset]);
  return preview;
}

function Effect({
  preview,
}: {
  preview: { data?: TermsPreview | undefined; isPending: boolean; error: unknown };
}) {
  if (preview.error) {
    return (
      <Alert tone="danger" className="mt-4">
        {messageOf(preview.error)}
      </Alert>
    );
  }
  const data = preview.data;
  if (!data) {
    return (
      <p className="mt-4 text-body-sm text-text-muted" aria-live="polite">
        {preview.isPending ? "Checking the effect…" : "Change a value to see its effect."}
      </p>
    );
  }
  return (
    <div
      className="mt-4 rounded-lg border border-border bg-surface-2 p-4"
      aria-live="polite"
      data-testid="terms-effect"
    >
      <p className="text-body-sm font-medium text-text">{data.message}</p>
      <p className="mt-1 text-body-sm text-text-muted tabular">
        Eligible bids: {data.before.eligible} now, {data.after.eligible} after.
        {data.after.team_cost.complete
          ? ` Cheapest full team: ${formatMoney(data.after.team_cost.total_paisa)}.`
          : ""}
      </p>
    </div>
  );
}

export function TooFewDialog({
  open,
  onOpenChange,
  project,
  view,
  onChanged,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: Project;
  view: ClientBids;
  onChanged: () => void;
}) {
  const [action, setAction] = useState<Action>("extend");
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title="Fix the shortfall"
      description="Pick one change. Each shows its effect on the eligible bids before you confirm."
    >
      <Tabs
        label="Ways to get enough eligible bids"
        value={action}
        onValueChange={(v) => {
          setAction(v as Action);
        }}
        items={[
          {
            value: "extend",
            label: "Extend",
            content: <ExtendPanel project={project} view={view} onDone={onChanged} />,
          },
          {
            value: "standards",
            label: "Lower standards",
            content: <StandardsPanel project={project} view={view} onDone={onChanged} />,
          },
          {
            value: "budget",
            label: "Raise budget",
            content: <BudgetPanel project={project} view={view} onDone={onChanged} />,
          },
          {
            value: "team",
            label: "Reduce team",
            content: <TeamPanel project={project} view={view} onDone={onChanged} />,
          },
          {
            value: "cancel",
            label: "Cancel",
            content: <CancelPanel project={project} onDone={onChanged} />,
          },
        ]}
      />
    </Dialog>
  );
}

interface PanelProps {
  project: Project;
  view: ClientBids;
  onDone: () => void;
}

function ApplyButton({
  label,
  change,
  project,
  onDone,
  success,
}: {
  label: string;
  change: TermsChange | null;
  project: Project;
  onDone: () => void;
  success: string;
}) {
  const apply = useChangeTerms(project.id);
  return (
    <>
      {apply.error ? (
        <Alert tone="danger" className="mt-4">
          {messageOf(apply.error)}
        </Alert>
      ) : null}
      <div className="mt-4 flex justify-end">
        <Button
          disabled={!change}
          loading={apply.isPending}
          onClick={() => {
            if (!change) return;
            apply.mutate(change, {
              onSuccess: () => {
                toast({ tone: "success", title: success });
                onDone();
              },
            });
          }}
        >
          {label}
        </Button>
      </div>
    </>
  );
}

function ExtendPanel({ project, view, onDone }: PanelProps) {
  const extend = useExtendBidding(project.id);
  const { extensions_used: used, max_extensions: max, extend_days: days } = view.bidding;
  const left = max - used;
  return (
    <div className="pt-4">
      <p className="text-body-sm text-text">
        {view.bidding.deadline
          ? `Bidding ${view.bidding.closed ? "closed" : "closes"} on ${formatDate(view.bidding.deadline)}. `
          : ""}
        Extending gives developers {days} more days to bid. You can extend {left} more{" "}
        {left === 1 ? "time" : "times"} ({used} of {max} used).
      </p>
      {extend.error ? (
        <Alert tone="danger" className="mt-4">
          {messageOf(extend.error)}
        </Alert>
      ) : null}
      <div className="mt-4 flex justify-end">
        <Button
          disabled={left <= 0}
          loading={extend.isPending}
          onClick={() => {
            extend.mutate(undefined, {
              onSuccess: () => {
                toast({ tone: "success", title: `Bidding extended by ${String(days)} days` });
                onDone();
              },
            });
          }}
        >
          Extend bidding by {days} days
        </Button>
      </div>
    </div>
  );
}

const pct = (score: number) => Math.round(score * 100);

function StandardsPanel({ project, view, onDone }: PanelProps) {
  const t = view.thresholds;
  const [perf, setPerf] = useState(pct(t.p0));
  const [comp, setComp] = useState(pct(t.c0));
  const change: TermsChange | null =
    perf !== pct(t.p0) || comp !== pct(t.c0)
      ? {
          ...(perf !== pct(t.p0) ? { min_performance: (perf / 100).toFixed(2) } : {}),
          ...(comp !== pct(t.c0) ? { min_competency: (comp / 100).toFixed(2) } : {}),
        }
      : null;
  const preview = useEffectPreview(project.id, change);
  return (
    <div className="space-y-5 pt-4">
      <p className="text-body-sm text-text-muted">
        DevSync already relaxes the minimums by up to {pct(t.p0 - t.floor_p0)} points when bids are
        short. You can lower your project’s own minimum down to {pct(t.floor_p0)} for performance
        and {pct(t.floor_c0)} for competency.
      </p>
      <Slider
        label="Minimum performance"
        value={perf}
        onChange={setPerf}
        min={pct(t.floor_p0)}
        max={pct(t.default_p0)}
        step={5}
      />
      <Slider
        label="Minimum competency"
        value={comp}
        onChange={setComp}
        min={pct(t.floor_c0)}
        max={pct(t.default_c0)}
        step={5}
      />
      <Effect preview={preview} />
      <ApplyButton
        label="Lower the standards"
        change={change}
        project={project}
        onDone={onDone}
        success="Minimum standards updated"
      />
    </div>
  );
}

function BudgetPanel({ project, view, onDone }: PanelProps) {
  const currentTaka = Math.round(view.budget_paisa / 100);
  const [taka, setTaka] = useState(String(currentTaka));
  const value = Number.parseInt(taka, 10);
  const valid = Number.isFinite(value) && value > currentTaka;
  const change: TermsChange | null = valid ? { budget_paisa: value * 100 } : null;
  const preview = useEffectPreview(project.id, change);
  return (
    <div className="pt-4">
      <Field
        label="New budget (৳)"
        inputMode="numeric"
        hint={`Now ${formatMoney(view.budget_paisa)}. The budget can only go up.`}
        value={taka}
        onChange={(e) => {
          setTaka(e.target.value.replace(/[^\d]/g, ""));
        }}
      />
      <Effect preview={preview} />
      <ApplyButton
        label="Raise the budget"
        change={change}
        project={project}
        onDone={onDone}
        success="Budget raised"
      />
    </div>
  );
}

function TeamPanel({ project, view, onDone }: PanelProps) {
  const [counts, setCounts] = useState<Record<string, number>>(() =>
    Object.fromEntries(view.coverage.map((c) => [c.slot_id, c.needed])),
  );
  const changed = view.coverage.filter((c) => counts[c.slot_id] !== c.needed);
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const change: TermsChange | null =
    changed.length > 0 && total >= 2
      ? { slot_counts: changed.map((c) => ({ slot_id: c.slot_id, count: counts[c.slot_id] ?? 1 })) }
      : null;
  const preview = useEffectPreview(project.id, change);
  return (
    <div className="space-y-4 pt-4">
      <p className="text-body-sm text-text-muted">
        Hire fewer people per slot. A team needs at least 2 people; places can only be removed here.
      </p>
      <ul className="space-y-3">
        {view.coverage.map((c) => (
          <li key={c.slot_id} className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-body-sm text-text">
              {c.slot_label} <span className="text-text-muted">({c.eligible} eligible)</span>
            </span>
            <span className="w-32">
              <Select
                aria-label={`People for ${c.slot_label}`}
                value={String(counts[c.slot_id] ?? c.needed)}
                onChange={(v) => {
                  setCounts((prev) => ({ ...prev, [c.slot_id]: Number(v) }));
                }}
                options={Array.from({ length: c.needed }, (_, i) => ({
                  value: String(i + 1),
                  label: `${String(i + 1)} ${i === 0 ? "person" : "people"}`,
                }))}
              />
            </span>
          </li>
        ))}
      </ul>
      {total < 2 ? <Alert tone="warning">A team needs at least 2 people.</Alert> : null}
      <Effect preview={preview} />
      <ApplyButton
        label="Reduce the team"
        change={change}
        project={project}
        onDone={onDone}
        success="Team reduced"
      />
    </div>
  );
}

function CancelPanel({ project, onDone }: { project: Project; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [typed, setTyped] = useState("");
  const cancel = useCancelProject(project.id);
  const ready = reason.trim().length >= 3 && typed.trim() === project.title.trim();
  return (
    <div className="space-y-4 pt-4">
      <p className="text-body-sm text-text-muted">
        Cancelling is free before a team is formed. Every bidder is told the project closed.
      </p>
      <FormField label="Reason" hint="Shared with anyone who bid.">
        {(a11y) => (
          <Textarea
            {...a11y}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
            }}
            rows={3}
            maxLength={500}
          />
        )}
      </FormField>
      <Field
        label={`Type “${project.title}” to confirm`}
        autoComplete="off"
        value={typed}
        onChange={(e) => {
          setTyped(e.target.value);
        }}
      />
      {cancel.error ? <Alert tone="danger">{messageOf(cancel.error)}</Alert> : null}
      <div className="flex justify-end">
        <Button
          variant="destructive"
          disabled={!ready}
          loading={cancel.isPending}
          onClick={() => {
            cancel.mutate(
              { reason: reason.trim() },
              {
                onSuccess: () => {
                  toast({ tone: "success", title: "Project cancelled" });
                  onDone();
                },
              },
            );
          }}
        >
          Cancel project
        </Button>
      </div>
    </div>
  );
}
