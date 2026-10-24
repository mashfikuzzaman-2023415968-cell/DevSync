import { CirclePlus } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import type { ProjectListItem } from "@/api/types";
import { NodeArt } from "@/components/brand/NodeArt";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState, PageHeader, StatCard } from "@/components/ui/Feedback";
import { useMe } from "@/features/auth/api";
import { useMyProjectsOverview } from "@/features/projects/api";
import {
  ACTIVE_STATUSES,
  PROJECT_STATUS_TONE,
  projectNextAction,
  projectStatusLabel,
  projectStatusWords,
} from "@/features/projects/status";
import { formatDate, formatDateTime, formatMoney, formatRelative } from "@/lib/format";
import { Checklist } from "./Checklist";
import { firstName, greeting } from "./greeting";

const LIST_LIMIT = 6;
const ACTIVITY_LIMIT = 5;

/** Most recently updated first. */
function byUpdated(a: ProjectListItem, b: ProjectListItem): number {
  return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
}

/** Client dashboard (spec §13.5 #20): stats, the latest projects with their next step, and
 * recent activity from the client's real projects. Approvals and the wallet join with payments
 * (Phase 10). */
export default function ClientHome() {
  const me = useMe();
  const user = me.data;
  const projects = useMyProjectsOverview();
  const verified = user?.phone_verified === true && user.email_verified;

  const createAction = (
    <Button asChild>
      <Link to="/client/projects/new">
        <CirclePlus aria-hidden="true" />
        Create project
      </Link>
    </Button>
  );

  const checklist = verified ? null : (
    <Card>
      <CardHeader
        title="Before you publish"
        description="Both checks keep the marketplace trustworthy."
      />
      <div className="mt-2">
        <Checklist
          items={[
            {
              label: "Verify your phone",
              done: user?.phone_verified === true,
              hint: "One account per number.",
              to: "/verify",
            },
            {
              label: "Verify your email",
              done: user?.email_verified === true,
              hint: "Bids, invitations and approvals are sent there.",
              to: "/verify",
            },
          ]}
        />
      </div>
    </Card>
  );

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${firstName(user?.display_name)}`}
        description="Plan a project, get a balanced team and pay by milestone."
        action={createAction}
      />
      {projects.isPending ? (
        <Loading />
      ) : projects.isError ? (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
          <Card>
            <ErrorState
              title="Your projects didn’t load"
              requestId={projects.error instanceof ApiError ? projects.error.requestId : null}
              onRetry={() => void projects.refetch()}
            />
          </Card>
          {checklist}
        </div>
      ) : projects.data.items.length === 0 ? (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
          <Card>
            <EmptyState
              art={<NodeArt />}
              title="No projects yet"
              description="Describe the work, split it into milestones and DevSync shows the critical path before anyone bids."
              action={
                <Button asChild variant="outline">
                  <Link to="/client/projects/new">Plan your first project</Link>
                </Button>
              }
            />
          </Card>
          {checklist}
        </div>
      ) : (
        <Dashboard
          projects={projects.data.items}
          more={projects.data.next_cursor !== null}
          checklist={checklist}
        />
      )}
    </>
  );
}

function Loading() {
  return (
    <div aria-hidden="true" className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28 rounded-lg" />
        ))}
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <Skeleton className="h-72 rounded-lg" />
        <Skeleton className="h-48 rounded-lg" />
      </div>
    </div>
  );
}

function Dashboard({
  projects,
  more,
  checklist,
}: {
  projects: ProjectListItem[];
  /** Older projects exist beyond this page: the counts are lower bounds ("100+"). */
  more: boolean;
  checklist: ReactNode;
}) {
  const count = (pred: (p: ProjectListItem) => boolean) => projects.filter(pred).length;
  // With older projects beyond this page a count is a lower bound, shown as "3+".
  const atLeast = more
    ? { format: (v: number) => `${Math.round(v).toLocaleString("en-IN")}+` }
    : {};
  const recent = [...projects].sort(byUpdated);
  const listed = recent.filter((p) => p.status !== "CANCELLED").slice(0, LIST_LIMIT);
  const activity = recent.slice(0, ACTIVITY_LIMIT);

  return (
    <div className="space-y-6">
      <section aria-label="Project counts" className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          {...atLeast}
          label="Active projects"
          value={count((p) => ACTIVE_STATUSES.has(p.status))}
        />
        <StatCard {...atLeast} label="Open for bids" value={count((p) => p.status === "BIDDING")} />
        <StatCard {...atLeast} label="Drafts" value={count((p) => p.status === "DRAFT")} />
        <StatCard {...atLeast} label="Completed" value={count((p) => p.status === "COMPLETED")} />
      </section>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <Card>
          <CardHeader
            title="Your projects"
            description="The latest first, with what to do next."
            action={
              <Button asChild variant="ghost">
                <Link to="/client/projects">My projects</Link>
              </Button>
            }
          />
          {listed.length === 0 ? (
            <p className="p-5 text-body-sm text-text-muted">
              Every project so far was cancelled. Create a new one when you’re ready.
            </p>
          ) : (
            <ul className="mt-3 divide-y divide-border border-t border-border">
              {listed.map((p) => (
                <ProjectRow key={p.id} project={p} />
              ))}
            </ul>
          )}
        </Card>
        <div className="space-y-6">
          {checklist}
          <Card>
            <CardHeader title="Recent activity" description="Your latest project changes." />
            <ol className="space-y-4 p-5">
              {activity.map((p) => (
                <li key={p.id} className="min-w-0">
                  <p className="truncate text-body-sm font-medium text-text">{p.title}</p>
                  <p className="text-body-sm text-text-muted">
                    {projectStatusWords(p.status)},{" "}
                    <time dateTime={p.updated_at} title={formatDateTime(p.updated_at)}>
                      {formatRelative(p.updated_at)}
                    </time>
                  </p>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ProjectRow({ project: p }: { project: ProjectListItem }) {
  const next = projectNextAction(p);
  return (
    <li className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="min-w-0 truncate text-body font-medium text-text">{p.title}</h3>
          <Badge tone={PROJECT_STATUS_TONE[p.status] ?? "neutral"}>
            {projectStatusLabel(p.status)}
          </Badge>
        </div>
        <p className="mt-1 text-body-sm text-text-muted">
          Budget {formatMoney(p.budget_paisa)}, team of {p.team_size}
          {p.bidding_deadline ? `, bids close ${formatDate(p.bidding_deadline)}` : ""}
        </p>
      </div>
      <Button asChild variant="outline" className="shrink-0">
        <Link to={next.to} aria-label={`${next.label}: ${p.title}`}>
          {next.label}
        </Link>
      </Button>
    </li>
  );
}
