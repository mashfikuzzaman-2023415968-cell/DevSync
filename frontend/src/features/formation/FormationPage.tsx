/**
 * Team formation `/client/projects/:id/formation` (spec §13.5 #24, §13.9; Demo 2 centrepiece).
 *
 * Settings (left on wide screens): a preset, the four priority sliders (always 100 %), the
 * minimum standards with a live "x of y bids meet them", and the fairness dial; "Form team"
 * queues a run. While it runs the swarm indicator and a live convergence line follow the job's
 * event stream. The result: a stat row (team score, price against the budget, finish against the
 * deadline, the exact solver's verdict, the cost of fairness), a card per member with their
 * contribution, "Why this team?" with risks and the runner-up difference, the convergence chart,
 * the top three teams side by side, earlier runs, and "Confirm team" (FORMING → TEAM_PENDING;
 * invitations go out in Phase 8). Once confirmed the page shows the confirmed run read-only.
 */
import { CheckCircle2, ShieldCheck, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError } from "@/api/client";
import type {
  ClientBids,
  FormationRun,
  FormationRunCreate,
  FormationRunSummary,
  Preset,
  Project,
  RunResult,
} from "@/api/types";
import { ConvergenceChart, SwarmIndicator } from "@/components/ConvergenceChart";
import { FairnessDial, type Dial } from "@/components/FairnessDial";
import { PrioritySliders, toPercents, type Weights } from "@/components/PrioritySliders";
import { TERM_LABEL, TeamCard } from "@/components/TeamCard";
import { TeamComparison } from "@/components/TeamComparison";
import { Button } from "@/components/ui/Button";
import { Badge, Breadcrumbs, Card, CardHeader, RiskChip, Skeleton } from "@/components/ui/Display";
import type { Severity } from "@/components/ui/Display";
import { Alert, EmptyState, ErrorState, PageHeader, Progress } from "@/components/ui/Feedback";
import { ConfirmDialog } from "@/components/ui/Overlay";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Slider } from "@/components/ui/Slider";
import { toast } from "@/components/ui/toast-store";
import { formatDateTime, formatDays, formatMoney, formatPercent } from "@/lib/format";
import { useClientBids } from "@/features/bids/api";
import { useProject } from "@/features/projects/api";
import {
  useConfirmTeam,
  useFormationRun,
  useFormationRuns,
  useJobProgress,
  useStartRun,
} from "./api";

/** The presets' weights (DECISIONS D115: Balanced plus emphasis on one term). */
export const PRESET_WEIGHTS: Record<Preset, Weights> = {
  balanced: { competency: 0.35, teamwork: 0.25, time: 0.2, cost: 0.2 },
  quality: { competency: 0.675, teamwork: 0.125, time: 0.1, cost: 0.1 },
  fast: { competency: 0.175, teamwork: 0.125, time: 0.6, cost: 0.1 },
  budget: { competency: 0.175, teamwork: 0.125, time: 0.1, cost: 0.6 },
};
const PRESETS: readonly { value: Preset; label: string }[] = [
  { value: "balanced", label: "Balanced" },
  { value: "quality", label: "Quality" },
  { value: "fast", label: "Fast" },
  { value: "budget", label: "Budget" },
];
const RISK: Record<string, { severity: Severity; text: string }> = {
  SINGLE_POINT_SKILL: {
    severity: "MEDIUM",
    text: "Only one member has a skill a critical milestone needs",
  },
  BUDGET_TIGHT: { severity: "MEDIUM", text: "Uses more than 95% of the budget" },
  SCHEDULE_TIGHT: { severity: "MEDIUM", text: "Finishes close to the deadline" },
  LOW_TEAMWORK: { severity: "MEDIUM", text: "Teamwork scores are low" },
  NEWCOMER_ON_CRITICAL_PATH: { severity: "LOW", text: "A newcomer works on a critical milestone" },
};
const ACTIVE = new Set(["QUEUED", "RUNNING"]);

export default function FormationPage() {
  const { id = "" } = useParams();
  const project = useProject(id);
  const bids = useClientBids(id);
  const runs = useFormationRuns(id);

  if (project.isPending || bids.isPending || runs.isPending) {
    return (
      <>
        <PageHeader title="Form your team" />
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
          <Card className="p-5" aria-busy="true" aria-label="Loading team formation">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="mt-6 h-40 w-full" />
          </Card>
          <div className="grid gap-4 sm:grid-cols-2">
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
          </div>
        </div>
      </>
    );
  }
  const failed = [project, bids, runs].find((q) => q.isError);
  if (failed || !project.data || !bids.data || !runs.data) {
    const err = failed?.error;
    if (err instanceof ApiError && err.status === 404) {
      return (
        <>
          <PageHeader title="Project not found" />
          <Card>
            <EmptyState
              title="We couldn’t find that project"
              description="It may have been removed, or it isn’t one of yours."
              action={
                <Button asChild variant="outline">
                  <Link to="/client/projects">Back to my projects</Link>
                </Button>
              }
            />
          </Card>
        </>
      );
    }
    return (
      <>
        <PageHeader title="Form your team" />
        <Card>
          <ErrorState
            title="Team formation didn’t load"
            requestId={err instanceof ApiError ? err.requestId : null}
            onRetry={() => {
              void project.refetch();
              void bids.refetch();
              void runs.refetch();
            }}
          />
        </Card>
      </>
    );
  }
  return <Formation project={project.data} bids={bids.data} runs={runs.data} />;
}

function Formation({
  project,
  bids,
  runs,
}: {
  project: Project;
  bids: ClientBids;
  runs: FormationRunSummary[];
}) {
  const forming = project.status === "FORMING";
  const confirmed = runs.find((r) => r.confirmed);
  const [selected, setSelected] = useState<string | null>(confirmed?.id ?? runs[0]?.id ?? null);
  const [jobId, setJobId] = useState<string | null>(null);
  const run = useFormationRun(selected);
  const live = useJobProgress(jobId, () => {
    void run.refetch();
  });

  const crumbs = (
    <Breadcrumbs
      items={[
        { label: "My projects", to: "/client/projects" },
        { label: project.title, to: `/client/projects/${project.id}/bids` },
        { label: "Team formation" },
      ]}
    />
  );

  if (!forming && !confirmed) {
    return (
      <>
        <PageHeader title="Form your team" breadcrumbs={crumbs} />
        <Card>
          <EmptyState
            icon={<Users />}
            title={
              project.status === "BIDDING"
                ? "Bidding is still open"
                : "Team formation isn’t available"
            }
            description={
              project.status === "BIDDING"
                ? "Team formation opens when bidding closes with enough eligible bids."
                : "This project isn’t at the team formation stage."
            }
            action={
              <Button asChild variant="outline">
                <Link to={`/client/projects/${project.id}/bids`}>See the bids</Link>
              </Button>
            }
          />
        </Card>
      </>
    );
  }

  const running = Boolean(run.data && ACTIVE.has(run.data.status));
  return (
    <>
      <PageHeader
        title="Form your team"
        breadcrumbs={crumbs}
        description={`For “${project.title}”. DevSync searches every combination of eligible bids for the best team.`}
      />
      {confirmed ? (
        <Alert tone="success" title="Team confirmed" className="mb-6">
          The developers’ invitations go out next. Bids that weren’t chosen were told why.
        </Alert>
      ) : null}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-6">
          {forming ? (
            <Settings
              project={project}
              bids={bids}
              hasRun={runs.length > 0}
              running={running}
              onStarted={(runId, job) => {
                setSelected(runId);
                setJobId(job);
              }}
            />
          ) : null}
          {runs.length > 0 ? (
            <EarlierRuns runs={runs} selected={selected} onSelect={setSelected} />
          ) : null}
        </div>
        <div className="flex min-w-0 flex-col gap-6">
          {!selected ? (
            <Card>
              <EmptyState
                icon={<Users />}
                title="No team yet"
                description="Choose your priorities and select Form team. It takes a few seconds."
              />
            </Card>
          ) : run.isPending ? (
            <Card className="p-5" aria-busy="true" aria-label="Loading the run">
              <Skeleton className="h-24 w-full" />
            </Card>
          ) : run.isError ? (
            <Card>
              <ErrorState
                title="This run didn’t load"
                requestId={run.error instanceof ApiError ? run.error.requestId : null}
                onRetry={() => void run.refetch()}
              />
            </Card>
          ) : (
            <RunView run={run.data} live={live} projectId={project.id} />
          )}
        </div>
      </div>
    </>
  );
}

// ------------------------------------------------------------------------------ settings

function Settings({
  project,
  bids,
  hasRun,
  running,
  onStarted,
}: {
  project: Project;
  bids: ClientBids;
  hasRun: boolean;
  running: boolean;
  onStarted: (runId: string, jobId: string) => void;
}) {
  const t = bids.thresholds;
  const [preset, setPreset] = useState<Preset>("balanced");
  const [weights, setWeights] = useState<Weights>(toPercents(PRESET_WEIGHTS.balanced));
  const [custom, setCustom] = useState(false);
  const [minP, setMinP] = useState(Math.round(t.p0 * 100));
  const [minC, setMinC] = useState(Math.round(t.c0 * 100));
  const shortlistedNewcomers = bids.bids.filter((b) => b.is_newcomer && b.shortlisted).length;
  const [dial, setDial] = useState<Dial>(shortlistedNewcomers > 0 ? "1" : "0");
  const start = useStartRun(project.id);

  const standing = bids.bids.filter((b) => b.status === "ACTIVE" || b.status === "INELIGIBLE");
  const passing = standing.filter(
    (b) =>
      b.eligible && (b.is_newcomer || (b.performance * 100 >= minP && b.competency * 100 >= minC)),
  ).length;

  const submit = () => {
    const body: FormationRunCreate = { preset, min_newcomers: Number(dial) };
    if (custom) {
      body.weights = {
        competency: (weights.competency / 100).toFixed(3),
        teamwork: (weights.teamwork / 100).toFixed(3),
        time: (weights.time / 100).toFixed(3),
        cost: (weights.cost / 100).toFixed(3),
      };
    }
    if (minP !== Math.round(t.p0 * 100)) body.min_performance = (minP / 100).toFixed(3);
    if (minC !== Math.round(t.c0 * 100)) body.min_competency = (minC / 100).toFixed(3);
    start.mutate(body, {
      onSuccess: (r) => {
        onStarted(r.run_id, r.job_id);
      },
    });
  };
  const error = start.error instanceof ApiError ? start.error : null;

  return (
    <Card className="flex flex-col gap-6 p-5">
      <div className="space-y-2">
        <p className="text-body-sm font-semibold text-text" id="preset-label">
          Preset
        </p>
        <SegmentedControl
          label="Preset"
          value={preset}
          onChange={(p) => {
            setPreset(p);
            setCustom(false);
            setWeights(toPercents(PRESET_WEIGHTS[p]));
          }}
          segments={PRESETS}
          className="grid w-full grid-cols-2 sm:grid-cols-4 xl:grid-cols-2"
        />
        <p className="text-caption text-text-muted">
          {custom
            ? "Your own priorities."
            : {
                balanced: "Weighs skill, teamwork, speed and cost evenly.",
                quality: "Puts the most skilled developers first.",
                fast: "Puts the quickest delivery first.",
                budget: "Keeps the price as low as it can.",
              }[preset]}
        </p>
      </div>
      <PrioritySliders
        value={weights}
        onChange={(w) => {
          setWeights(w);
          setCustom(true);
        }}
      />
      <fieldset className="space-y-4">
        <legend className="text-body-sm font-semibold text-text">Minimum standards</legend>
        <Slider
          label="Performance"
          value={minP}
          min={Math.round(t.floor_p0 * 100)}
          max={100}
          onChange={setMinP}
        />
        <Slider
          label="Competency"
          value={minC}
          min={Math.round(t.floor_c0 * 100)}
          max={100}
          onChange={setMinC}
        />
        <p className="text-caption text-text-muted" aria-live="polite">
          {passing} of {standing.length} bids meet these standards. Newcomers are judged by their
          tests instead.
        </p>
      </fieldset>
      <FairnessDial value={dial} onChange={setDial} newcomersAvailable={shortlistedNewcomers} />
      {error ? (
        <Alert tone="danger" title="The team search didn’t start">
          {error.message}
        </Alert>
      ) : null}
      <Button onClick={submit} loading={start.isPending} disabled={running}>
        {hasRun ? "Recalculate" : "Form team"}
      </Button>
    </Card>
  );
}

function EarlierRuns({
  runs,
  selected,
  onSelect,
}: {
  runs: FormationRunSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <Card>
      <CardHeader title="Runs" description="Every run is saved and can be reproduced." />
      <ul className="px-3 pb-3 pt-2">
        {runs.slice(0, 10).map((r) => (
          <li key={r.id}>
            <button
              type="button"
              onClick={() => {
                onSelect(r.id);
              }}
              aria-current={r.id === selected ? "true" : undefined}
              className="flex min-h-11 w-full items-center justify-between gap-3 rounded-md px-2 py-2 text-left text-body-sm hover:bg-surface-2 aria-[current=true]:bg-primary-soft"
            >
              <span className="min-w-0">
                <span className="block font-medium text-text">
                  {PRESETS.find((p) => p.value === r.preset)?.label ?? r.preset}, {r.min_newcomers}{" "}
                  {r.min_newcomers === 1 ? "newcomer" : "newcomers"}
                </span>
                <span className="block text-caption text-text-muted" data-volatile>
                  {formatDateTime(r.created_at)}
                </span>
              </span>
              <span className="shrink-0 tabular text-text">
                {r.confirmed ? (
                  <Badge tone="success">Confirmed</Badge>
                ) : r.fitness !== null ? (
                  r.fitness.toFixed(2)
                ) : (
                  <span className="text-text-muted">{statusText(r.status)}</span>
                )}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function statusText(status: string): string {
  return (
    {
      QUEUED: "Waiting",
      RUNNING: "Searching",
      INFEASIBLE: "No team",
      FAILED: "Failed",
      TIMED_OUT: "Time limit",
    }[status] ?? status
  );
}

// ---------------------------------------------------------------------------------- result

function RunView({
  run,
  live,
  projectId,
}: {
  run: FormationRun;
  live: ReturnType<typeof useJobProgress>;
  projectId: string;
}) {
  if (ACTIVE.has(run.status)) {
    return (
      <Card className="flex flex-col gap-5 p-5">
        <SwarmIndicator label="Searching for the best team…" />
        <Progress label="Search progress" value={Math.max(live.progress, 1)} max={100} />
        <ConvergenceChart values={live.best} iterations={live.iteration ?? 0} live />
      </Card>
    );
  }
  if (run.status === "FAILED") {
    return (
      <Card>
        <ErrorState
          title="The team search failed"
          description="Nothing was changed. Run it again; if it keeps failing, contact support with the reference below."
          requestId={run.error_code}
        />
      </Card>
    );
  }
  const result = run.result;
  if (!result || !result.feasible) {
    return (
      <Card>
        <EmptyState
          icon={<Users />}
          title="No team fits every requirement"
          description="Try fewer newcomers, lower minimum standards, or ask for more bids from the Bids page."
        />
      </Card>
    );
  }
  return <Result run={run} result={result} projectId={projectId} />;
}

function Result({
  run,
  result,
  projectId,
}: {
  run: FormationRun;
  result: RunResult;
  projectId: string;
}) {
  const confirm = useConfirmTeam(projectId);
  const names = useMemo(
    () => new Map(result.team.map((m) => [m.bid_id, m.developer_name] as const)),
    [result.team],
  );
  const scale = Math.max(
    0.0001,
    ...result.team.flatMap((m) => [
      Math.abs(m.contribution.comp),
      Math.abs(m.contribution.team),
      Math.abs(m.contribution.time),
      Math.abs(m.contribution.cost),
    ]),
  );
  const v = result.verification;
  const fair = result.fairness;
  const [shown, setShown] = useState(false);
  useEffect(() => {
    setShown(false);
  }, [run.id]);

  return (
    <>
      {run.status === "TIMED_OUT" ? (
        <Alert tone="warning" title="The search hit its time limit">
          This is the best team found in time. Run it again for a fuller search.
        </Alert>
      ) : null}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Team score" value={(result.fitness ?? 0).toFixed(2)}>
          {v.available ? (
            v.optimal ? (
              <span className="inline-flex items-center gap-1 text-success">
                <ShieldCheck className="size-3.5" aria-hidden="true" /> Optimal (exact check)
              </span>
            ) : (
              `Within ${formatPercent(v.gap ?? 0)} of the best`
            )
          ) : (
            "Too many bids for an exact check"
          )}
        </Stat>
        <Stat label="Price" value={formatMoney(result.price_paisa)}>
          of {formatMoney(result.budget_after_fee_paisa)} budget
        </Stat>
        <Stat label="Finish" value={formatDays(result.max_days)}>
          deadline {formatDays(result.deadline_days)}
        </Stat>
        <Stat label="Cost of fairness" value={formatPercent(fair.cost)}>
          {fair.applied_k > 0
            ? `${String(result.newcomers)} ${result.newcomers === 1 ? "newcomer" : "newcomers"} included`
            : "No newcomer minimum"}
        </Stat>
      </div>
      {fair.reason === "MAX_FEASIBLE_K" ? (
        <Alert tone="info" title={`Only ${String(fair.applied_k)} newcomers could fit`}>
          You asked for {fair.requested_k}; no team with more fits the budget and deadline.
        </Alert>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
        {result.team.map((m) => (
          <TeamCard key={m.bid_id} member={m} scale={scale} />
        ))}
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 2xl:grid-cols-2">
        <WhyThisTeam result={result} />
        <Card>
          <CardHeader title="How the search converged" />
          {/* The curve depends on the run's server-chosen seed (masked in visual baselines). */}
          <div className="px-5 pb-5 pt-3" data-volatile>
            <ConvergenceChart values={result.convergence} iterations={result.iterations} />
          </div>
        </Card>
      </div>
      {result.top.length > 1 ? (
        <Card>
          <CardHeader
            title="Compare the best teams"
            description="The next best teams the search found, for comparison."
            action={
              <Button
                variant="outline"
                aria-expanded={shown}
                onClick={() => {
                  setShown((s) => !s);
                }}
              >
                {shown ? "Hide" : "Compare"}
              </Button>
            }
          />
          {shown ? (
            <div className="px-5 pb-5 pt-3">
              <TeamComparison teams={result.top} names={names} />
            </div>
          ) : (
            <div className="pb-5" />
          )}
        </Card>
      ) : null}
      {run.can_confirm ? (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
          {confirm.error instanceof ApiError ? (
            <p className="text-body-sm text-danger" role="alert">
              {confirm.error.message}
            </p>
          ) : null}
          <ConfirmDialog
            destructive={false}
            title="Confirm this team?"
            description={`${String(result.team.length)} developers will be invited (invitations go out next). The other bids are told they weren’t selected, and no more runs can be made.`}
            confirmLabel="Confirm team"
            onConfirm={async () => {
              await confirm.mutateAsync(run.id);
              toast({ tone: "success", title: "Team confirmed" });
            }}
            trigger={
              <Button>
                <CheckCircle2 className="size-5" aria-hidden="true" />
                Confirm team
              </Button>
            }
          />
        </div>
      ) : null}
    </>
  );
}

function Stat({
  label,
  value,
  children,
}: {
  label: string;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-4">
      <p className="text-body-sm text-text-muted">{label}</p>
      <p className="mt-1 text-h4 font-semibold tabular text-text">{value}</p>
      <p className="mt-1 text-caption text-text-muted">{children}</p>
    </Card>
  );
}

function WhyThisTeam({ result }: { result: RunResult }) {
  const term = result.deciding_term;
  return (
    <Card>
      <CardHeader title="Why this team?" />
      <div className="space-y-4 px-5 pb-5 pt-3 text-body-sm">
        <p className="text-text">
          It covers every role
          {result.newcomers > 0
            ? `, includes ${String(result.newcomers)} ${result.newcomers === 1 ? "newcomer" : "newcomers"}`
            : ""}{" "}
          and fits the budget and deadline.
          {term
            ? ` Chosen over the next best team mainly for its ${TERM_LABEL[term].toLowerCase()}.`
            : ""}
        </p>
        <div>
          <div className="mb-1.5 flex justify-between gap-3">
            <span className="text-text">Budget used</span>
            <span className="tabular text-text-muted">{formatPercent(result.budget_share)}</span>
          </div>
          <Progress
            label={`Budget used: ${formatPercent(result.budget_share)}`}
            value={Math.round(result.budget_share * 100)}
            max={100}
            tone={result.budget_share > 0.95 ? "warning" : "success"}
          />
        </div>
        <div>
          <div className="mb-1.5 flex justify-between gap-3">
            <span className="text-text">Time of the deadline</span>
            <span className="tabular text-text-muted">{formatPercent(result.schedule_share)}</span>
          </div>
          <Progress
            label={`Time of the deadline: ${formatPercent(result.schedule_share)}`}
            value={Math.round(result.schedule_share * 100)}
            max={100}
            tone={result.schedule_share > 0.9 ? "warning" : "success"}
          />
        </div>
        <div>
          <p className="font-medium text-text">Risks</p>
          {result.risks.length === 0 ? (
            <p className="mt-1 text-text-muted">None found.</p>
          ) : (
            <ul className="mt-2 flex flex-wrap gap-2">
              {result.risks.map((r) => {
                const risk = RISK[r] ?? { severity: "LOW" as const, text: r };
                return (
                  <li key={r}>
                    <RiskChip severity={risk.severity}>{risk.text}</RiskChip>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        {result.relaxations.length > 0 ? (
          <p className="text-text-muted">
            The minimum standards were relaxed {result.relaxations.length}{" "}
            {result.relaxations.length === 1 ? "step" : "steps"} to find enough candidates.
          </p>
        ) : null}
      </div>
    </Card>
  );
}
