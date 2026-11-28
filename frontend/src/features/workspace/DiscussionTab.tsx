/**
 * Discussion tab `/w/:projectId/discussion` (spec §13.4, §10.2 Discussion; D146): the project's
 * threads, most recently active first, and the open thread's conversation (`?thread=` keeps it
 * in the address, so a mention notification opens it). Everyone on the project reads and writes
 * while it is in progress; posts are plain text with picked mentions, refreshed every 15 seconds.
 * On phones the list and the thread take turns on the screen.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, MessagesSquare, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router";
import { z } from "zod";
import { ApiError } from "@/api/client";
import type { Thread } from "@/api/types";
import { Comments } from "@/components/Comments";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { Alert, EmptyState, ErrorState } from "@/components/ui/Feedback";
import { Field, FormField, Textarea } from "@/components/ui/Field";
import { toast } from "@/components/ui/toast-store";
import { useMe } from "@/features/auth/api";
import { applyFieldErrors, messageFor } from "@/features/auth/errors";
import { cn } from "@/lib/cn";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useWorkspace } from "./context";
import { useCreateThread, useThreads } from "./discussionApi";

export const threadSchema = z.object({
  title: z
    .string()
    .trim()
    .min(3, "Give the thread a title of at least 3 characters")
    .max(120, "Keep the title under 120 characters"),
  body: z.string().trim().min(1, "Write the first post").max(4000, "At most 4,000 characters"),
});
type ThreadForm = z.infer<typeof threadSchema>;

export default function DiscussionTab() {
  const ws = useWorkspace();
  const me = useMe();
  const q = useThreads(ws.projectId);
  const [params, setParams] = useSearchParams();
  const [starting, setStarting] = useState(false);
  const openId = params.get("thread");
  const writable = ws.team.project_status === "IN_PROGRESS";
  const people = useMemo(
    () =>
      ws.team.members
        .filter((m) => m.status === "ACTIVE")
        .map((m) => ({ id: m.developer_id, name: m.developer_name })),
    [ws.team.members],
  );
  const select = (id: string | null) => {
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (id) next.set("thread", id);
      else next.delete("thread");
      return next;
    });
  };

  if (q.isPending) {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Loading threads">
        <Skeleton className="h-16 w-full rounded-lg" />
        <Skeleton className="h-16 w-full rounded-lg" />
      </div>
    );
  }
  if (q.isError) {
    return (
      <Card>
        <ErrorState
          title="The discussion didn’t load"
          requestId={q.error instanceof ApiError ? q.error.requestId : null}
          onRetry={() => void q.refetch()}
        />
      </Card>
    );
  }
  const threads = q.data.pages.flatMap((p) => p.items);
  const open = threads.find((t) => t.id === openId) ?? null;
  const meRef = me.data ? { id: me.data.id, name: me.data.display_name } : null;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)]">
      <section
        aria-labelledby="threads-heading"
        className={cn("space-y-3", openId && "hidden lg:block")}
      >
        <div className="flex items-center justify-between gap-3">
          <h2 id="threads-heading" className="text-body font-semibold">
            Threads
          </h2>
          {writable && !starting ? (
            <Button size="sm" onClick={() => { setStarting(true); }}>
              <Plus className="size-4" aria-hidden="true" /> New thread
            </Button>
          ) : null}
        </div>
        {starting ? (
          <NewThread
            projectId={ws.projectId}
            onDone={(t) => {
              setStarting(false);
              if (t) select(t.id);
            }}
          />
        ) : null}
        {threads.length === 0 && !starting ? (
          <Card>
            <EmptyState
              icon={<MessagesSquare />}
              title="No threads yet"
              description="Start one for anything that isn’t about a single task: plans, decisions, questions for the client."
            />
          </Card>
        ) : (
          <ul className="space-y-2">
            {threads.map((t) => (
              <li key={t.id}>
                <ThreadButton thread={t} active={t.id === openId} onOpen={() => { select(t.id); }} />
              </li>
            ))}
          </ul>
        )}
        {q.hasNextPage ? (
          <Button variant="outline" loading={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
            Show older threads
          </Button>
        ) : null}
      </section>

      <section aria-label="Open thread" className={cn(!openId && "hidden lg:block")}>
        {open ? (
          <Card className="p-5">
            <Button variant="ghost" size="sm" className="mb-3 lg:hidden" onClick={() => { select(null); }}>
              <ArrowLeft className="size-4" aria-hidden="true" /> All threads
            </Button>
            <h2 className="break-words text-h4 font-semibold">{open.title}</h2>
            <p className="mb-4 text-caption text-text-muted">
              Started by {open.created_by.name} on {formatDateTime(open.created_at)}
            </p>
            <Comments
              targetType="DISCUSSION_POST"
              targetId={open.id}
              people={people}
              me={meRef}
              canWrite={writable && me.data?.role !== "ADMIN"}
              label="Posts"
              writeLabel="Write a post"
              sendLabel="Post"
            />
          </Card>
        ) : openId ? (
          <Card>
            <EmptyState
              icon={<MessagesSquare />}
              title="This thread isn’t here"
              description="It may be on an older page of threads, or the link is wrong."
              action={
                <Button variant="outline" onClick={() => { select(null); }}>
                  All threads
                </Button>
              }
            />
          </Card>
        ) : (
          <Card>
            <EmptyState
              icon={<MessagesSquare />}
              title="Choose a thread"
              description="Pick a thread on the left to read and reply."
            />
          </Card>
        )}
      </section>
    </div>
  );
}

function ThreadButton({ thread, active, onOpen }: { thread: Thread; active: boolean; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-current={active ? "true" : undefined}
      className={cn(
        "w-full rounded-lg border border-border bg-surface p-3 text-left transition-colors duration-fast ease-standard hover:bg-surface-2",
        active && "border-primary bg-primary-soft",
      )}
    >
      <span className="block break-words font-medium text-text">{thread.title}</span>
      <span className="block text-caption text-text-muted" title={formatDateTime(thread.last_post_at)}>
        {thread.post_count} {thread.post_count === 1 ? "post" : "posts"}, last{" "}
        {formatRelative(thread.last_post_at)}
      </span>
    </button>
  );
}

function NewThread({ projectId, onDone }: { projectId: string; onDone: (t: Thread | null) => void }) {
  const create = useCreateThread(projectId);
  const [notice, setNotice] = useState<string | null>(null);
  const form = useForm<ThreadForm>({
    resolver: zodResolver(threadSchema),
    defaultValues: { title: "", body: "" },
  });
  const submit = form.handleSubmit(async (v) => {
    setNotice(null);
    try {
      const t = await create.mutateAsync({ title: v.title, body: v.body, mention_ids: [] });
      toast({ tone: "success", title: "Thread started" });
      onDone(t);
    } catch (e) {
      if (!applyFieldErrors(e, form.setError, ["title", "body"])) setNotice(messageFor(e));
    }
  });
  const errors = form.formState.errors;
  return (
    <Card>
      <CardHeader title="New thread" description="Everyone on the project can read and reply." />
      <form noValidate onSubmit={(e) => void submit(e)} className="space-y-3 px-5 pb-5">
        {notice ? <Alert tone="danger">{notice}</Alert> : null}
        <Field label="Title" maxLength={120} error={errors.title?.message} {...form.register("title")} />
        <FormField label="First post" required error={errors.body?.message}>
          <Textarea rows={4} maxLength={4000} {...form.register("body")} />
        </FormField>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" loading={form.formState.isSubmitting}>
            Start thread
          </Button>
          <Button variant="ghost" onClick={() => { onDone(null); }}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}
