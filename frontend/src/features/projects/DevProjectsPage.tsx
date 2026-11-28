/**
 * My projects for developers `/dev/projects` (spec §13.5 #13): the teams you're in and the ones
 * you finished, each with its progress, next deadline and overall risk, opening the workspace.
 */
import { FolderKanban } from "lucide-react";
import { Link, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Card, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useMyProjects, type MyProjectsState } from "./myProjectsApi";
import { MyProjectRow } from "./ProjectPulse";

const SEGMENTS: { value: MyProjectsState; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "completed", label: "Completed" },
];

export default function DevProjectsPage() {
  const [params, setParams] = useSearchParams();
  const state: MyProjectsState = params.get("state") === "completed" ? "completed" : "active";
  const q = useMyProjects(state);
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <PageHeader
        title="My projects"
        description="The teams you work in, with progress and what’s due next."
      />
      <SegmentedControl<MyProjectsState>
        label="Which projects"
        value={state}
        onChange={(v) => {
          setParams(v === "active" ? {} : { state: v });
        }}
        segments={SEGMENTS}
        className="mb-6 w-full sm:w-auto"
      />
      {q.isPending ? (
        <div className="space-y-3" aria-busy="true" aria-label="Loading your projects">
          <Skeleton className="h-24 w-full rounded-lg" />
          <Skeleton className="h-24 w-full rounded-lg" />
        </div>
      ) : q.isError ? (
        <Card>
          <ErrorState
            title="Your projects didn’t load"
            requestId={q.error instanceof ApiError ? q.error.requestId : null}
            onRetry={() => void q.refetch()}
          />
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<FolderKanban />}
            title={state === "active" ? "No active projects yet" : "No finished projects yet"}
            description={
              state === "active"
                ? "When a client picks you for a team, the project appears here."
                : "Projects you complete stay here, with what you did on them."
            }
            action={
              state === "active" ? (
                <Button asChild variant="outline">
                  <Link to="/dev/find">Browse open projects</Link>
                </Button>
              ) : undefined
            }
          />
        </Card>
      ) : (
        <>
          <ul className="grid gap-3 lg:grid-cols-2">
            {items.map((p) => (
              <li key={p.project_id}>
                <MyProjectRow p={p} />
              </li>
            ))}
          </ul>
          {q.hasNextPage ? (
            <Button
              variant="outline"
              className="mt-4"
              loading={q.isFetchingNextPage}
              onClick={() => void q.fetchNextPage()}
            >
              Show more
            </Button>
          ) : null}
        </>
      )}
    </>
  );
}
