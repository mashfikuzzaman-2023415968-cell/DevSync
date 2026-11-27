/**
 * Workspace task hooks (spec §10.2 Tasks, §13.7; D143, D144, D158, D172).
 *
 * The board reads one cursor-paged query per column (50 cards, then "Show more"), so a long
 * column never has to load at once and drag targets stay real DOM (no virtualisation, D158).
 * Moves are optimistic: the card jumps to its new place at once and goes back, with the server's
 * reason, if the move is refused or the task changed meanwhile (409).
 */
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
} from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  EvidenceCreate,
  TaskCard,
  TaskCreate,
  TaskDetail,
  TaskEvidence,
  TaskPage,
  TaskPatch,
  TaskStatus,
} from "@/api/types";

export const STATUSES: readonly TaskStatus[] = ["TODO", "IN_PROGRESS", "REVIEW", "DONE"];
export const STATUS_LABEL: Record<TaskStatus, string> = {
  TODO: "To do",
  IN_PROGRESS: "In progress",
  REVIEW: "Review",
  DONE: "Done",
};
export const PROGRESS: Record<TaskStatus, number> = {
  TODO: 0,
  IN_PROGRESS: 50,
  REVIEW: 85,
  DONE: 100,
};
export const COLUMN_PAGE = 50;

export interface BoardFilters {
  milestoneId?: string | undefined;
  assigneeId?: string | undefined;
  mine?: boolean | undefined;
}

export const taskKeys = {
  board: (projectId: string) => ["projects", projectId, "tasks"] as const,
  column: (projectId: string, status: TaskStatus, f: BoardFilters) =>
    [
      "projects",
      projectId,
      "tasks",
      status,
      f.milestoneId ?? "all",
      f.assigneeId ?? "all",
      f.mine ? "mine" : "everyone",
    ] as const,
  task: (taskId: string) => ["tasks", taskId] as const,
};

function query(status: TaskStatus, f: BoardFilters, cursor: string | null): string {
  const p = new URLSearchParams({ status, limit: String(COLUMN_PAGE) });
  if (f.milestoneId) p.set("milestone_id", f.milestoneId);
  if (f.assigneeId) p.set("assignee_id", f.assigneeId);
  if (f.mine) p.set("mine", "true");
  if (cursor) p.set("cursor", cursor);
  return p.toString();
}

/** One column of the board, 50 cards per page. */
export function useColumn(projectId: string, status: TaskStatus, filters: BoardFilters) {
  return useInfiniteQuery({
    queryKey: taskKeys.column(projectId, status, filters),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api<TaskPage>(`/projects/${projectId}/tasks?${query(status, filters, pageParam)}`),
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: 30_000,
  });
}

export function useTask(taskId: string | null) {
  return useQuery({
    queryKey: taskKeys.task(taskId ?? "none"),
    enabled: taskId !== null,
    retry: false,
    queryFn: () => api<TaskDetail>(`/tasks/${taskId ?? ""}`),
  });
}

function refreshBoard(qc: QueryClient, projectId: string, taskId?: string) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: taskKeys.board(projectId) }),
    ...(taskId ? [qc.invalidateQueries({ queryKey: taskKeys.task(taskId) })] : []),
    qc.invalidateQueries({ queryKey: ["projects", projectId, "dashboard"] }),
    qc.invalidateQueries({ queryKey: ["projects", projectId, "plan"] }),
  ]);
}

export function useCreateTask(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({ milestoneId, body }: { milestoneId: string; body: TaskCreate }) =>
      api<TaskDetail>(`/milestones/${milestoneId}/tasks`, { method: "POST", body }),
    onSuccess: () => refreshBoard(qc, projectId),
  });
}

export function usePatchTask(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({ task, body }: { task: TaskDetail; body: TaskPatch }) =>
      api<TaskDetail>(`/tasks/${task.id}`, {
        method: "PATCH",
        body,
        headers: { "If-Match": String(task.version) },
      }),
    onSuccess: (task) => refreshBoard(qc, projectId, task.id),
  });
}

export function useDeleteTask(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (task: TaskCard) =>
      api<null>(`/tasks/${task.id}`, {
        method: "DELETE",
        headers: { "If-Match": String(task.version) },
      }),
    onSuccess: (_r, task) => refreshBoard(qc, projectId, task.id),
  });
}

export interface MoveRequest {
  task: TaskCard;
  status: TaskStatus;
  /** The card above the drop place and the card below it, in the target column. */
  afterId?: string | null | undefined;
  beforeId?: string | null | undefined;
}

type ColumnData = InfiniteData<TaskPage, string | null>;

/** Put `card` into `column` between the named neighbours (or at the end), locally. */
export function placeCard(
  cards: TaskCard[],
  card: TaskCard,
  afterId: string | null | undefined,
  beforeId: string | null | undefined,
): TaskCard[] {
  const rest = cards.filter((c) => c.id !== card.id);
  let index = rest.length;
  if (afterId) {
    const i = rest.findIndex((c) => c.id === afterId);
    if (i >= 0) index = i + 1;
  } else if (beforeId) {
    const i = rest.findIndex((c) => c.id === beforeId);
    if (i >= 0) index = i;
  }
  return [...rest.slice(0, index), card, ...rest.slice(index)];
}

function rewrite(data: ColumnData | undefined, f: (cards: TaskCard[]) => TaskCard[]) {
  if (!data) return data;
  const all = f(data.pages.flatMap((p) => p.items));
  // Keep the page boundaries the server sent (the cursor of the last page still holds).
  let offset = 0;
  const pages = data.pages.map((p, i) => {
    const size = i === data.pages.length - 1 ? all.length - offset : p.items.length;
    const items = all.slice(offset, offset + size);
    offset += size;
    return { ...p, items };
  });
  return { ...data, pages };
}

/** Move a task (one step, or within its column): optimistic, rolled back on any refusal. */
export function useMoveTask(projectId: string, filters: BoardFilters) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({ task, status, afterId, beforeId }: MoveRequest) =>
      api<TaskCard>(`/tasks/${task.id}/move`, {
        method: "POST",
        body: { status, after_id: afterId ?? null, before_id: beforeId ?? null },
        headers: { "If-Match": String(task.version) },
      }),
    onMutate: async ({ task, status, afterId, beforeId }) => {
      const from = taskKeys.column(projectId, task.status, filters);
      const to = taskKeys.column(projectId, status, filters);
      await qc.cancelQueries({ queryKey: taskKeys.board(projectId) });
      const before = {
        from: qc.getQueryData<ColumnData>(from),
        to: qc.getQueryData<ColumnData>(to),
      };
      const moved: TaskCard = { ...task, status, progress_pct: PROGRESS[status] };
      if (task.status !== status) {
        qc.setQueryData<ColumnData>(from, (d) =>
          rewrite(d, (cards) => cards.filter((c) => c.id !== task.id)),
        );
      }
      qc.setQueryData<ColumnData>(to, (d) =>
        rewrite(d, (cards) => placeCard(cards, moved, afterId, beforeId)),
      );
      return { before, from, to };
    },
    onError: (_err, _req, ctx) => {
      if (!ctx) return;
      qc.setQueryData(ctx.from, ctx.before.from);
      qc.setQueryData(ctx.to, ctx.before.to);
    },
    onSettled: (_r, _e, req) => refreshBoard(qc, projectId, req.task.id),
  });
}

export function useAddDependency(projectId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (dependsOn: string) =>
      api<unknown>(`/tasks/${taskId}/dependencies`, {
        method: "POST",
        body: { depends_on_task_id: dependsOn },
      }),
    onSuccess: () => refreshBoard(qc, projectId, taskId),
  });
}

export function useRemoveDependency(projectId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (dependsOn: string) =>
      api<null>(`/tasks/${taskId}/dependencies/${dependsOn}`, { method: "DELETE" }),
    onSuccess: () => refreshBoard(qc, projectId, taskId),
  });
}

export function useAddEvidence(projectId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: EvidenceCreate) =>
      api<TaskEvidence>(`/tasks/${taskId}/evidence`, { method: "POST", body }),
    onSuccess: () => refreshBoard(qc, projectId, taskId),
  });
}
