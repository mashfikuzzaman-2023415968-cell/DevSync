/** Project and CPM-planner data hooks (spec §7.3, §9.10, §10.2 Projects). */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { refreshMe } from "@/features/auth/api";
import type {
  CancelIn,
  CpmPreview,
  Dependency,
  Milestone,
  MilestoneIn,
  Plan,
  PlanPreviewIn,
  Project,
  ProjectCreate,
  ProjectDraft,
  ProjectListPage,
  ProjectUpdate,
  PublishIn,
  Slot,
  SlotIn,
} from "@/api/types";

export const keys = {
  list: ["projects", "mine"] as const,
  project: (id: string) => ["projects", id] as const,
  slots: (id: string) => ["projects", id, "slots"] as const,
  milestones: (id: string) => ["projects", id, "milestones"] as const,
  dependencies: (id: string) => ["projects", id, "dependencies"] as const,
  plan: (id: string) => ["projects", id, "plan"] as const,
  draft: (id: string) => ["projects", id, "draft"] as const,
};

function myProjectsPath(cursor: string | null, limit?: number): string {
  const p = new URLSearchParams();
  if (limit !== undefined) p.set("limit", String(limit));
  if (cursor) p.set("cursor", cursor);
  const qs = p.toString();
  return `/projects${qs ? `?${qs}` : ""}`;
}

/** My projects, newest first, a cursor page at a time ("Load more", spec §10.1). */
export function useMyProjects() {
  return useInfiniteQuery({
    queryKey: keys.list,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => api<ProjectListPage>(myProjectsPath(pageParam)),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

/** The dashboard's view: the newest `OVERVIEW_LIMIT` projects in one page. `more` says the
 * client has older ones too, so counts drawn from these are "at least". */
export const OVERVIEW_LIMIT = 100;
export function useMyProjectsOverview() {
  return useQuery({
    queryKey: [...keys.list, "overview"] as const,
    queryFn: () => api<ProjectListPage>(myProjectsPath(null, OVERVIEW_LIMIT)),
  });
}

export function useProject(id: string) {
  return useQuery({
    queryKey: keys.project(id),
    queryFn: () => api<Project>(`/projects/${id}`),
  });
}

/** A saved draft with its slots, milestones and dependencies, to reopen the wizard (D55).
 * Fetched once per visit: the wizard owns the state from then on. */
export function useProjectDraft(id: string | null) {
  return useQuery({
    queryKey: keys.draft(id ?? ""),
    queryFn: () => api<ProjectDraft>(`/projects/${id ?? ""}/draft`),
    enabled: id !== null,
    retry: false,
    staleTime: Infinity,
    gcTime: 0,
  });
}

export function useProjectPlan(id: string) {
  return useQuery({
    queryKey: keys.plan(id),
    retry: false,
    queryFn: () => api<Plan>(`/projects/${id}/plan`),
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: ProjectCreate) => api<Project>("/projects", { method: "POST", body }),
    onSuccess: (project) => {
      qc.setQueryData(keys.project(project.id), project);
      void qc.invalidateQueries({ queryKey: keys.list });
    },
  });
}

/** Patch a DRAFT; sends the current version via If-Match so stale saves 409. `projectId`
 * overrides the hook's id: the wizard creates the draft and patches it in the same click,
 * before a re-render could hand the hook the new id. */
export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({
      body,
      version,
      projectId = id,
    }: {
      body: ProjectUpdate;
      version: number;
      projectId?: string;
    }) =>
      api<Project>(`/projects/${projectId}`, {
        method: "PATCH",
        body,
        headers: { "If-Match": String(version) },
      }),
    onSuccess: (project) => {
      qc.setQueryData(keys.project(project.id), project);
      void qc.invalidateQueries({ queryKey: keys.list });
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (id: string) => api<undefined>(`/projects/${id}`, { method: "DELETE" }),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.list }),
  });
}

/** A whole-set replace's saved rows and the project's new version (`X-Version`; null if the
 * server didn't send one, then the caller re-reads the project). */
export interface Replaced<T> {
  items: T;
  version: number | null;
}

/** PUT a whole set with `If-Match: <version>` (spec §10.1); a stale version is a 409. */
async function replaceSet<T>(path: string, body: unknown, version?: number): Promise<Replaced<T>> {
  let next: number | null = null;
  const items = await api<T>(path, {
    method: "PUT",
    body,
    ...(version === undefined ? {} : { headers: { "If-Match": String(version) } }),
    onHeaders: (headers) => {
      const value = Number(headers.get("X-Version"));
      next = Number.isInteger(value) && value > 0 ? value : null;
    },
  });
  return { items, version: next };
}

export function useReplaceSlots(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({ slots, version }: { slots: SlotIn[]; version?: number }) =>
      replaceSet<Slot[]>(`/projects/${id}/slots`, { slots }, version),
    onSuccess: ({ items }) => {
      qc.setQueryData(keys.slots(id), items);
      void qc.invalidateQueries({ queryKey: keys.project(id) });
    },
  });
}

export function useReplaceMilestones(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({ milestones, version }: { milestones: MilestoneIn[]; version?: number }) =>
      replaceSet<Milestone[]>(`/projects/${id}/milestones`, { milestones }, version),
    onSuccess: ({ items }) => qc.setQueryData(keys.milestones(id), items),
  });
}

export function useReplaceDependencies(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({ dependencies, version }: { dependencies: Dependency[]; version?: number }) =>
      replaceSet<Dependency[]>(`/projects/${id}/dependencies`, { dependencies }, version),
    onSuccess: ({ items }) => qc.setQueryData(keys.dependencies(id), items),
  });
}

/** Run CPM on an unsaved plan to preview the timeline and warnings (no persistence). */
export function usePlanPreview(id: string) {
  return useMutation({
    mutationFn: (body: PlanPreviewIn) =>
      api<CpmPreview>(`/projects/${id}/plan/preview`, { method: "POST", body }),
  });
}

export function usePublishProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: PublishIn) =>
      api<Project>(`/projects/${id}/publish`, { method: "POST", body }),
    onSuccess: (project) => {
      qc.setQueryData(keys.project(id), project);
      void qc.invalidateQueries({ queryKey: keys.list });
      void qc.invalidateQueries({ queryKey: keys.plan(id) });
    },
  });
}

export function useCancelProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: CancelIn) =>
      api<Project>(`/projects/${id}/cancel`, { method: "POST", body }),
    onSuccess: (project) => {
      qc.setQueryData(keys.project(id), project);
      void qc.invalidateQueries({ queryKey: keys.list });
    },
  });
}

export function useExtendBidding(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: () => api<Project>(`/projects/${id}/extend-bidding`, { method: "POST" }),
    onSuccess: (project) => {
      qc.setQueryData(keys.project(id), project);
      void qc.invalidateQueries({ queryKey: keys.list });
    },
  });
}

/** Verify the client's (simulated) payment method; publishing needs it (D39). */
export function useVerifyPaymentMethod() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: () => api<undefined>("/me/payment-method/verify", { method: "POST" }),
    onSuccess: () => refreshMe(qc),
  });
}
