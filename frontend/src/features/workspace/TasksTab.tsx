/**
 * Tasks tab `/w/:projectId/tasks` (spec §13.5 #30, §13.9 "Kanban (Demo 2)"; D143, D158).
 *
 * The board with filters (milestone, assignee, only mine), the task drawer (`?task=<id>`, so
 * notifications can link straight to a task) and, for the lead, "New task" (a floating button on
 * phones). Members move their own tasks, the lead moves any; the client sees the same board with
 * no handles, menus or task actions (§1.6). Moves are optimistic and roll back with the reason.
 */
import { ClipboardList, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import type { TaskCard, TaskStatus } from "@/api/types";
import { KanbanBoard, type KanbanColumn, type KanbanMove } from "@/components/KanbanBoard";
import { Button } from "@/components/ui/Button";
import { Card, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { Switch } from "@/components/ui/Choice";
import { Select } from "@/components/ui/Select";
import { toast } from "@/components/ui/toast-store";
import { messageFor } from "@/features/auth/errors";
import { useProjectPlan } from "@/features/projects/api";
import { STATUSES, STATUS_LABEL, useColumn, useMoveTask, type BoardFilters } from "./api";
import { TaskDrawer } from "./TaskDrawer";
import { TaskFormDialog } from "./TaskFormDialog";
import { useWorkspace } from "./context";

const ALL = "all";
const ORDER: Record<TaskStatus, number> = { TODO: 0, IN_PROGRESS: 1, REVIEW: 2, DONE: 3 };

/** Today in Asia/Dhaka as YYYY-MM-DD. */
export function dhakaToday(now: Date = new Date()): string {
  return now.toLocaleDateString("en-CA", { timeZone: "Asia/Dhaka" });
}

/** The board's own check before asking the server (it re-checks everything, D143). */
export function boardRefusal(card: TaskCard, target: TaskStatus): string | null {
  const step = ORDER[target] - ORDER[card.status];
  if (Math.abs(step) !== 1) {
    const next = STATUSES[ORDER[card.status] + (step > 0 ? 1 : -1)];
    return next ? `Move it to ${STATUS_LABEL[next]} first.` : null;
  }
  if (target === "DONE" && card.blocked_by > 0) return "Finish the tasks it waits for first.";
  return null;
}

export default function TasksTab() {
  const ws = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [filters, setFilters] = useState<BoardFilters>({});
  const [creating, setCreating] = useState(false);
  const plan = useProjectPlan(ws.projectId);
  const todo = useColumn(ws.projectId, "TODO", filters);
  const doing = useColumn(ws.projectId, "IN_PROGRESS", filters);
  const review = useColumn(ws.projectId, "REVIEW", filters);
  const done = useColumn(ws.projectId, "DONE", filters);
  const columns = [
    { status: "TODO" as const, q: todo },
    { status: "IN_PROGRESS" as const, q: doing },
    { status: "REVIEW" as const, q: review },
    { status: "DONE" as const, q: done },
  ];
  const move = useMoveTask(ws.projectId, filters);
  const taskId = params.get("task");

  const milestones = useMemo(
    () => (plan.data?.nodes ?? []).map((n) => ({ value: n.key, label: n.name })),
    [plan.data],
  );
  const members = useMemo(
    () =>
      ws.team.members
        .filter((m) => m.status === "ACTIVE")
        .map((m) => ({ value: m.developer_id, label: m.developer_name })),
    [ws.team.members],
  );
  const cards = columns.flatMap((c) => c.q.data?.pages.flatMap((p) => p.items) ?? []);

  const open = (card: TaskCard) => {
    setParams((p) => ({ ...Object.fromEntries(p), task: card.id }));
  };
  const close = () => {
    setParams((p) => {
      const next = new URLSearchParams(p);
      next.delete("task");
      return next;
    });
  };
  const doMove = ({ card, status, afterId, beforeId }: KanbanMove) => {
    move.mutate(
      { task: card, status, afterId, beforeId },
      {
        onError: (e) =>
          toast({
            tone: "danger",
            title:
              e instanceof ApiError && e.status === 409
                ? "That move didn’t happen"
                : "Couldn’t move the task",
            description: messageFor(e),
          }),
      },
    );
  };

  if (columns.some((c) => c.q.isPending)) {
    return (
      <div className="grid gap-4 md:grid-cols-4" aria-busy="true" aria-label="Loading the board">
        {STATUSES.map((s) => (
          <Skeleton key={s} className="h-64 w-full rounded-xl" />
        ))}
      </div>
    );
  }
  const failed = columns.find((c) => c.q.isError);
  if (failed?.q.error) {
    const err = failed.q.error;
    return (
      <Card>
        <ErrorState
          title="The board didn’t load"
          requestId={err instanceof ApiError ? err.requestId : null}
          onRetry={() => {
            columns.forEach((c) => void c.q.refetch());
          }}
        />
      </Card>
    );
  }

  const boardColumns: KanbanColumn[] = columns.map(({ status, q }) => ({
    status,
    label: STATUS_LABEL[status],
    cards: q.data?.pages.flatMap((p) => p.items) ?? [],
    hasMore: q.hasNextPage,
    loadingMore: q.isFetchingNextPage,
    onShowMore: () => void q.fetchNextPage(),
  }));
  const empty = cards.length === 0 && !filters.milestoneId && !filters.assigneeId && !filters.mine;
  const newTask = ws.isLead ? (
    <TaskFormDialog
      projectId={ws.projectId}
      milestones={milestones}
      members={members}
      open={creating}
      onOpenChange={setCreating}
      defaultMilestoneId={filters.milestoneId}
    />
  ) : null;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-full sm:w-56">
          <Select
            aria-label="Milestone"
            value={filters.milestoneId ?? ALL}
            onChange={(v) => {
              setFilters((f) => ({ ...f, milestoneId: v === ALL ? undefined : v }));
            }}
            options={[{ value: ALL, label: "All milestones" }, ...milestones]}
          />
        </div>
        <div className="w-full sm:w-56">
          <Select
            aria-label="Assignee"
            value={filters.assigneeId ?? ALL}
            onChange={(v) => {
              setFilters((f) => ({ ...f, assigneeId: v === ALL ? undefined : v }));
            }}
            options={[{ value: ALL, label: "Everyone" }, ...members]}
          />
        </div>
        {ws.myUserId ? (
          <Switch
            label="Only mine"
            className="justify-start"
            checked={Boolean(filters.mine)}
            onCheckedChange={(on) => {
              setFilters((f) => ({ ...f, mine: on || undefined }));
            }}
          />
        ) : null}
        {ws.isLead ? (
          <Button
            className="ml-auto hidden md:inline-flex"
            onClick={() => {
              setCreating(true);
            }}
          >
            <Plus className="size-5" aria-hidden="true" /> New task
          </Button>
        ) : null}
      </div>
      {empty ? (
        <Card>
          <EmptyState
            icon={<ClipboardList />}
            title="No tasks yet"
            description={
              ws.isLead
                ? "Break the active milestone into tasks so the team can start."
                : "The team lead adds tasks here; you’ll see them as soon as they do."
            }
            action={
              ws.isLead ? (
                <Button
                  onClick={() => {
                    setCreating(true);
                  }}
                >
                  New task
                </Button>
              ) : undefined
            }
          />
        </Card>
      ) : (
        <KanbanBoard
          columns={boardColumns}
          readOnly={ws.isClient}
          canMove={(c) => ws.isLead || (ws.myUserId !== null && c.assignee?.id === ws.myUserId)}
          refusal={boardRefusal}
          onMove={doMove}
          onRefused={(reason) => toast({ tone: "warning", title: reason })}
          onOpen={open}
          today={dhakaToday()}
        />
      )}
      {ws.isLead ? (
        <Button
          className="fixed bottom-[calc(5rem+env(safe-area-inset-bottom))] right-4 z-30 size-14 rounded-full shadow-lg md:hidden"
          aria-label="New task"
          onClick={() => {
            setCreating(true);
          }}
        >
          <Plus className="size-6" aria-hidden="true" />
        </Button>
      ) : null}
      {newTask}
      <TaskDrawer
        projectId={ws.projectId}
        taskId={taskId}
        onClose={close}
        onMove={(task, status) => {
          doMove({ card: task, status, afterId: null, beforeId: null });
        }}
        candidates={cards}
        milestones={milestones}
        members={members}
        myUserId={ws.myUserId}
        writable={ws.team.project_status === "IN_PROGRESS"}
      />
    </>
  );
}
