/**
 * The project workspace `/w/:projectId/*` (spec §13.4, §13.5 #29–39; D120, D141, D160).
 *
 * One header and the §13.4 tab bar (eleven tabs, as real links), then the tab's page. Only the
 * project's client and its members get here (the API answers 404 to anyone else). The client
 * reads everything and may comment, post and upload, and nothing else (§1.6); a project that
 * hasn't started yet shows only the Team tab. Tabs that later phases fill say which phase.
 */
import { Users } from "lucide-react";
import { Link, Navigate, NavLink, Outlet, useParams } from "react-router";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Card, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { useTeam } from "@/features/team/api";
import { cn } from "@/lib/cn";
import { useWorkspace, WORKSPACE_TABS, workspaceContext } from "./context";

/** Tabs with a page in this build; the rest show as coming, never as dead links. */
const BUILT = new Set([
  "overview",
  "tasks",
  "timeline",
  "milestones",
  "team",
  "check-ins",
  "files",
  "risks",
]);

export default function WorkspaceLayout() {
  const { projectId = "" } = useParams();
  const q = useTeam(projectId);
  if (q.isPending) {
    return (
      <>
        <PageHeader title="Workspace" />
        <Card className="p-5" aria-busy="true" aria-label="Loading the workspace">
          <Skeleton className="h-40 w-full" />
        </Card>
      </>
    );
  }
  if (q.isError) {
    const err = q.error;
    return (
      <>
        <PageHeader title="Workspace" />
        <Card>
          {err instanceof ApiError && err.status === 404 ? (
            <EmptyState
              icon={<Users />}
              title="We couldn’t find that workspace"
              description="It may not exist, or you aren’t on this project’s team."
            />
          ) : (
            <ErrorState
              title="The workspace didn’t load"
              requestId={err instanceof ApiError ? err.requestId : null}
              onRetry={() => void q.refetch()}
            />
          )}
        </Card>
      </>
    );
  }
  const ctx = workspaceContext(q.data);
  return (
    <>
      <PageHeader
        title={q.data.project_title}
        description={
          ctx.started ? "In progress." : "Waiting to start: the other tabs open when it does."
        }
        action={
          ctx.isClient ? (
            <Button asChild variant="outline">
              <Link to={`/client/projects/${projectId}/team`}>Manage team</Link>
            </Button>
          ) : null
        }
      />
      {/* `relative`: the sr-only notes are absolutely positioned; without a positioned ancestor
          inside the scroller they escape its clipping and widen the page on phones. */}
      <nav aria-label="Workspace" className="relative -mx-4 mb-6 overflow-x-auto px-4">
        <ul className="flex min-w-max gap-1 border-b border-border">
          {WORKSPACE_TABS.map((tab) => {
            const open = BUILT.has(tab.path) && (ctx.started || tab.path === "team");
            if (!open) {
              const why = tab.later
                ? `arrives in ${tab.later}`
                : ctx.started
                  ? "is on its way"
                  : "opens when the project starts";
              return (
                <li key={tab.path}>
                  <span
                    className="inline-flex min-h-11 items-center px-3 text-body-sm text-text-muted"
                    title={`${tab.label} ${why}`}
                  >
                    {tab.label}
                    <span className="sr-only"> ({why})</span>
                  </span>
                </li>
              );
            }
            return (
              <li key={tab.path}>
                <NavLink
                  to={tab.path}
                  className={({ isActive }) =>
                    cn(
                      "inline-flex min-h-11 items-center border-b-2 px-3 text-body-sm",
                      isActive
                        ? "border-primary font-medium text-text"
                        : "border-transparent text-text-muted hover:text-text",
                    )
                  }
                >
                  {tab.label}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
      <Outlet context={ctx} />
    </>
  );
}

/** `/w/:projectId`: the Overview once the project has started, the team before. */
export function WorkspaceIndex() {
  const ws = useWorkspace();
  return <Navigate to={ws.started ? "overview" : "team"} replace />;
}
