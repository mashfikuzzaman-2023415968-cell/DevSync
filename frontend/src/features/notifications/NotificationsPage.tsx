/**
 * Notifications `/notifications` (spec §13.5 #18; D122): your notifications grouped by day
 * (Asia/Dhaka), an unread dot, "Mark all read", and each one opening its page (a validated app
 * path, or none). The live stream and preferences arrive in Phase 9.
 */
import { Bell } from "lucide-react";
import { useNavigate } from "react-router";
import { ApiError } from "@/api/client";
import type { NotificationItem } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Card, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { cn } from "@/lib/cn";
import { formatDate, formatRelative } from "@/lib/format";
import { useMarkRead, useNotifications, useReadAll } from "./api";

function groups(items: NotificationItem[]): [string, NotificationItem[]][] {
  const out = new Map<string, NotificationItem[]>();
  for (const n of items) {
    const day = formatDate(n.created_at);
    out.set(day, [...(out.get(day) ?? []), n]);
  }
  return [...out.entries()];
}

export default function NotificationsPage() {
  const q = useNotifications();
  const markRead = useMarkRead();
  const readAll = useReadAll();
  const navigate = useNavigate();
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const unread = items.some((n) => !n.read_at);
  return (
    <>
      <PageHeader
        title="Notifications"
        description="What happened on your projects."
        action={
          unread ? (
            <Button
              variant="outline"
              loading={readAll.isPending}
              onClick={() => {
                readAll.mutate();
              }}
            >
              Mark all read
            </Button>
          ) : null
        }
      />
      {q.isPending ? (
        <Card className="p-5" aria-busy="true" aria-label="Loading notifications">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="mt-3 h-16 w-full" />
        </Card>
      ) : q.isError ? (
        <Card>
          <ErrorState
            title="Your notifications didn’t load"
            requestId={q.error instanceof ApiError ? q.error.requestId : null}
            onRetry={() => void q.refetch()}
          />
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Bell />}
            title="Nothing yet"
            description="Invitations, bids and project updates appear here."
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-6">
          {groups(items).map(([day, list]) => (
            <section key={day} aria-label={day}>
              <h2 className="mb-2 text-body-sm font-semibold text-text-muted" data-volatile>
                {day}
              </h2>
              <Card>
                <ul className="divide-y divide-border">
                  {list.map((n) => (
                    <li key={n.id}>
                      <button
                        type="button"
                        className="flex w-full min-h-11 items-start gap-3 px-5 py-4 text-left hover:bg-surface-2"
                        onClick={() => {
                          if (!n.read_at) markRead.mutate(n.id);
                          if (n.link_path) void navigate(n.link_path);
                        }}
                      >
                        <span
                          className={cn(
                            "mt-1.5 size-2 shrink-0 rounded-full",
                            n.read_at ? "bg-transparent" : "bg-primary",
                          )}
                          aria-hidden="true"
                        />
                        <span className="min-w-0">
                          <span
                            className={cn(
                              "block text-body-sm text-text",
                              !n.read_at && "font-semibold",
                            )}
                          >
                            {n.title}
                            {!n.read_at ? <span className="sr-only"> (unread)</span> : null}
                          </span>
                          <span className="block text-body-sm text-text-muted">{n.body}</span>
                          <span className="block text-caption text-text-subtle" data-volatile>
                            {formatRelative(n.created_at)}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </Card>
            </section>
          ))}
          {q.hasNextPage ? (
            <Button
              variant="outline"
              loading={q.isFetchingNextPage}
              onClick={() => void q.fetchNextPage()}
            >
              Load more
            </Button>
          ) : null}
        </div>
      )}
    </>
  );
}
