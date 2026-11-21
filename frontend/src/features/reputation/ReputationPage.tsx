/**
 * Reputation `/dev/reputation` (spec §13.5 #16, §13.9 "Reputation page (Demo 2)").
 *
 * The developer's own reputation: the six parameters with plain labels, competency and
 * performance (ReputationPanel), a radar of the six, the trend of competency and performance over
 * their projects, and "Why did this change?" — every project with one plain sentence per change
 * (from the server's log, D65 style). A newcomer gets a card explaining where their starting
 * values come from and what raises them. Values computed from simulated histories are labelled
 * as such (D84, §0.2 rule 6). Every data view has its loading, empty, error and success states.
 */
import { History, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import type { DeveloperReputation, ReputationHistoryItem } from "@/api/types";
import { RadarChart } from "@/components/RadarChart";
import { ReputationPanel } from "@/components/ReputationPanel";
import { TrendChart } from "@/components/TrendChart";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardHeader, NewcomerBadge, Skeleton } from "@/components/ui/Display";
import { Alert, EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { useMe } from "@/features/auth/api";
import { formatDate, formatScore } from "@/lib/format";
import { PARAMETERS, domainLabel, toNumber } from "@/lib/reputation";
import { useDeveloperReputation, useMyReputationHistory } from "./api";

const FIRST_PROJECTS = 5;

function plural(n: number, word: string): string {
  return `${String(n)} ${word}${n === 1 ? "" : "s"}`;
}

function headerDescription(rep: DeveloperReputation): string {
  const threshold = rep.newcomer?.threshold ?? 3;
  if (rep.is_newcomer) {
    return `You’re a newcomer: ${String(rep.completed_projects)} of ${String(threshold)} projects done.`;
  }
  return `Based on ${plural(rep.completed_projects, "completed project")} for ${plural(rep.distinct_clients, "client")}.`;
}

function LoadingState() {
  return (
    <>
      <PageHeader title="Your reputation" />
      <div
        className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]"
        aria-busy="true"
        aria-label="Loading your reputation"
      >
        <Card className="p-5">
          <Skeleton className="h-6 w-40" />
          <div className="mt-6 grid gap-6 md:grid-cols-2">
            {[0, 1].map((i) => (
              <div key={i} className="space-y-4">
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-2 w-full" />
                <Skeleton className="h-2 w-full" />
                <Skeleton className="h-2 w-full" />
              </div>
            ))}
          </div>
        </Card>
        <Card className="p-5">
          <Skeleton className="mx-auto h-56 w-56 rounded-full" />
        </Card>
      </div>
    </>
  );
}

function NewcomerCard({ rep }: { rep: DeveloperReputation }) {
  const basis = rep.newcomer;
  if (!basis) return null;
  const x = toNumber(rep.parameters.x);
  const omega = toNumber(rep.parameters.omega);
  return (
    <Card className="p-5">
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-newcomer-bg text-newcomer">
          <Sparkles className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 className="text-body font-semibold text-text">
            Where your starting values come from
          </h2>
          <p className="mt-0.5 text-body-sm text-text-muted">
            Until you’ve completed {plural(basis.threshold, "project")}, DevSync starts you from
            what you can already show. Your bids are filtered on your role assessment result, not on
            performance.
          </p>
        </div>
      </div>
      <ul className="mt-4 space-y-3 text-body-sm text-text">
        <li>
          <span className="font-medium">Communication {x !== null ? formatScore(x) : "—"}</span>:
          you have {String(basis.verified_items)} of 4 verified items (phone, email, a complete
          profile, a verified certificate). Each one raises it.
        </li>
        <li>
          <span className="font-medium">Expertise {omega !== null ? formatScore(omega) : "—"}</span>
          : you’ve passed a skill check in {plural(basis.evidence_domains, "area")}.
        </li>
        <li>
          <span className="font-medium">Quality {formatScore(Number(basis.review_default))}</span>:
          the platform’s average, until your first client rating.
        </li>
        <li>
          <span className="font-medium">
            Teamwork {formatScore(toNumber(rep.parameters.xm) ?? 0)}, client diversity{" "}
            {formatScore(toNumber(rep.parameters.mu) ?? 0)} and punctuality{" "}
            {formatScore(toNumber(rep.parameters.t) ?? 0)}
          </span>
          : a neutral start until your projects show otherwise.
        </li>
      </ul>
      <div className="mt-5 flex flex-wrap gap-3">
        <Button asChild variant="outline">
          <Link to="/dev/profile">Complete your profile</Link>
        </Button>
        <Button asChild variant="ghost">
          <Link to="/dev/find">Find a project to bid on</Link>
        </Button>
      </div>
    </Card>
  );
}

function trendOf(items: readonly ReputationHistoryItem[]) {
  const oldestFirst = [...items].reverse();
  const value = (item: ReputationHistoryItem, key: string) => {
    const change = item.changes.find((c) => c.parameter === key);
    return change ? toNumber(change.new) : null;
  };
  return {
    points: oldestFirst.map((i) => ({
      label: i.project_label,
      detail: formatDate(i.completed_at),
    })),
    series: [
      { name: "Competency", values: oldestFirst.map((i) => value(i, "c")) },
      { name: "Performance", values: oldestFirst.map((i) => value(i, "p")) },
    ],
  };
}

function ChangeList({ items }: { items: readonly ReputationHistoryItem[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, FIRST_PROJECTS);
  return (
    <>
      <ol className="divide-y divide-border">
        {shown.map((item) => {
          const changed = item.changes.filter((c) => c.old !== c.new);
          return (
            <li key={item.history_id} className="px-5 py-4">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <h3 className="text-body font-semibold text-text">{item.project_label}</h3>
                <p className="text-body-sm text-text-muted">
                  {domainLabel(item.domain)} project, finished {formatDate(item.completed_at)}
                </p>
              </div>
              {changed.length ? (
                <ul className="mt-2 space-y-1.5 text-body-sm text-text">
                  {changed.map((c) => (
                    <li key={c.parameter} className="[overflow-wrap:anywhere]">
                      {c.reason}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-body-sm text-text-muted">
                  Nothing changed after this project.
                </p>
              )}
            </li>
          );
        })}
      </ol>
      {items.length > FIRST_PROJECTS ? (
        <div className="border-t border-border px-5 py-3">
          <Button
            variant="ghost"
            onClick={() => {
              setAll((v) => !v);
            }}
          >
            {all ? "Show the latest 5 projects" : `Show all ${String(items.length)} projects`}
          </Button>
        </div>
      ) : null}
    </>
  );
}

function HistorySection() {
  const history = useMyReputationHistory();
  if (history.isPending) {
    return (
      <Card className="p-5" aria-busy="true" aria-label="Loading your reputation history">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="mt-4 h-40 w-full" />
      </Card>
    );
  }
  if (history.isError) {
    const err = history.error;
    return (
      <Card>
        <ErrorState
          title="Your reputation history didn’t load"
          requestId={err instanceof ApiError ? err.requestId : null}
          onRetry={() => void history.refetch()}
        />
      </Card>
    );
  }
  const items = history.data.items;
  if (!items.length) {
    return (
      <Card>
        <EmptyState
          icon={<History aria-hidden="true" />}
          title="No completed projects yet"
          description="Each project you finish updates your reputation, and this page will show what changed and why."
          action={
            <Button asChild>
              <Link to="/dev/find">Find projects</Link>
            </Button>
          }
        />
      </Card>
    );
  }
  const trend = trendOf(items);
  return (
    <>
      <Card>
        <CardHeader
          title="Trend over your projects"
          description="Competency and performance after each completed project, oldest first."
        />
        <div className="p-5 pt-4">
          {items.length > 1 ? (
            <TrendChart
              title="Competency and performance by project"
              points={trend.points}
              series={trend.series}
            />
          ) : (
            <p className="text-body-sm text-text-muted">
              Your trend appears after your second project.
            </p>
          )}
        </div>
      </Card>
      <Card>
        <CardHeader
          title="Why did this change?"
          description="What each project changed, newest first, with the reason."
        />
        <div className="mt-3">
          <ChangeList items={items} />
        </div>
      </Card>
    </>
  );
}

export default function ReputationPage() {
  const me = useMe();
  const rep = useDeveloperReputation(me.data?.id);

  if (me.isPending || rep.isPending) return <LoadingState />;
  if (rep.isError || me.isError || !me.data) {
    const err = rep.error ?? me.error;
    return (
      <>
        <PageHeader title="Your reputation" />
        <Card>
          <ErrorState
            title="Your reputation didn’t load"
            requestId={err instanceof ApiError ? err.requestId : null}
            onRetry={() => void rep.refetch()}
          />
        </Card>
      </>
    );
  }

  const data = rep.data;
  const radar = PARAMETERS.map((p) => ({
    label: p.label,
    value: toNumber(data.parameters[p.key]) ?? 0,
  }));
  return (
    <>
      <PageHeader title="Your reputation" description={headerDescription(data)}>
        <div className="flex flex-wrap gap-2">
          {data.is_newcomer ? <NewcomerBadge /> : null}
          {data.simulated ? <Badge tone="info">Simulated history</Badge> : null}
          {data.seeded ? <Badge tone="warning">Seeded demo value</Badge> : null}
        </div>
      </PageHeader>
      <div className="space-y-6">
        {data.simulated ? (
          <Alert tone="info">
            These projects come from DevSync’s market simulator, which stands in for real work until
            projects are completed and reviewed on the platform.
          </Alert>
        ) : null}
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
          <Card>
            <CardHeader
              title="Your parameters"
              description="Scores from 0 to 100. Clients see these on your profile and your bids."
            />
            <ReputationPanel reputation={data} showEvidence className="p-5" />
          </Card>
          <div className="space-y-6">
            <Card>
              <CardHeader title="At a glance" description="All six parameters on one chart." />
              <div className="p-5 pt-3">
                <RadarChart title="Your six reputation parameters" axes={radar} />
              </div>
            </Card>
            <NewcomerCard rep={data} />
          </div>
        </div>
        <HistorySection />
      </div>
    </>
  );
}
