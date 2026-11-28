/**
 * Evidence tab `/w/:projectId/evidence` (spec §13.4, §9.1.4–9.1.5; D144, D156): what each member
 * has visibly done on this project, from the evidence events only (no surveillance: no time
 * tracking, no screenshots of anyone's screen), and the full activity feed, newest first,
 * 20 at a time, virtualized once it is long. Every line is a plain sentence built by the server
 * from the event; nothing here is free text. Phase 11 builds reputation from the same events.
 */
import { Activity, ListChecks } from "lucide-react";
import { ApiError } from "@/api/client";
import type { ActivityItem, MemberEvidence } from "@/api/types";
import { VirtualList } from "@/components/VirtualList";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useWorkspace } from "./context";
import { useActivity, useEvidence } from "./monitoringApi";

const STATUS_LABEL: Record<string, string> = {
  ACTIVE: "Active",
  COMPLETED: "Completed",
  LEFT: "Left",
  REMOVED: "Removed",
};

export default function EvidenceTab() {
  const ws = useWorkspace();
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
      <MembersCard projectId={ws.projectId} />
      <FeedCard projectId={ws.projectId} />
    </div>
  );
}

function MembersCard({ projectId }: { projectId: string }) {
  const q = useEvidence(projectId);
  return (
    <Card>
      <CardHeader
        title="What each member has done"
        description="Counted from check-ins, finished tasks and conversations on this project. Phase 11 turns this into reputation."
      />
      <div className="px-5 pb-5">
        {q.isPending ? (
          <div className="space-y-3" aria-busy="true" aria-label="Loading evidence">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : q.isError ? (
          <ErrorState
            title="The evidence didn’t load"
            requestId={q.error instanceof ApiError ? q.error.requestId : null}
            onRetry={() => void q.refetch()}
          />
        ) : q.data.members.length === 0 ? (
          <EmptyState
            icon={<ListChecks />}
            title="No members yet"
            description="Evidence appears once the team starts work."
          />
        ) : (
          <ul className="grid gap-3 md:grid-cols-2">
            {q.data.members.map((m) => (
              <MemberRow key={m.member.id} m={m} />
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function MemberRow({ m }: { m: MemberEvidence }) {
  const facts: [string, string][] = [
    ["Check-ins on time", `${String(m.checkins_on_time)} of ${String(m.checkins_expected)}`],
    ["Tasks done", `${String(m.tasks_done)} (${m.hours_done} h estimated)`],
    ["Comments and posts", String(m.comments)],
    ["Replies to mentions", String(m.replies)],
    ["Blockers answered", String(m.blockers_answered)],
  ];
  return (
    <li className="rounded-lg border border-border p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-medium text-text">{m.member.name}</span>
        <span className="text-caption text-text-muted">{m.slot_label}</span>
        {m.status !== "ACTIVE" ? (
          <Badge tone="neutral" icon={false}>
            {STATUS_LABEL[m.status] ?? m.status}
          </Badge>
        ) : null}
      </div>
      <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-body-sm">
        {facts.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-text-muted">{label}</dt>
            <dd className="tabular text-right text-text">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-caption text-text-muted">
        {m.last_active_at ? (
          <span title={formatDateTime(m.last_active_at)}>
            Last active {formatRelative(m.last_active_at)}
          </span>
        ) : (
          "No activity yet"
        )}
      </p>
    </li>
  );
}

function FeedCard({ projectId }: { projectId: string }) {
  const q = useActivity(projectId, 20);
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <Card>
      <CardHeader
        title="Activity"
        description="Everything that counts as evidence, newest first."
      />
      <div className="px-5 pb-5">
        {q.isPending ? (
          <Skeleton className="h-32 w-full" />
        ) : q.isError ? (
          <ErrorState
            title="The activity didn’t load"
            requestId={q.error instanceof ApiError ? q.error.requestId : null}
            onRetry={() => void q.refetch()}
          />
        ) : items.length === 0 ? (
          <p className="text-body-sm text-text-muted">Nothing yet.</p>
        ) : (
          <>
            <VirtualList
              items={items}
              getKey={(a) => a.id}
              estimate={48}
              gap={8}
              aria-label="Activity"
              className="text-body-sm"
              render={(a) => <ActivityRow a={a} />}
            />
            {q.hasNextPage ? (
              <Button
                variant="outline"
                className="mt-3"
                loading={q.isFetchingNextPage}
                onClick={() => void q.fetchNextPage()}
              >
                Show earlier activity
              </Button>
            ) : null}
          </>
        )}
      </div>
    </Card>
  );
}

function ActivityRow({ a }: { a: ActivityItem }) {
  return (
    <div className="flex items-start gap-2">
      <Activity className="mt-0.5 size-4 shrink-0 text-text-subtle" aria-hidden="true" />
      <span className="min-w-0 flex-1 text-text">{a.summary}</span>
      <time
        className="shrink-0 text-caption text-text-muted"
        dateTime={a.at}
        title={formatDateTime(a.at)}
        data-volatile
      >
        {formatRelative(a.at)}
      </time>
    </div>
  );
}
