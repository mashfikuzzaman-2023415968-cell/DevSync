/** Project and CPM-planner data hooks (spec §7.3, §9.10, §10.2 Projects). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
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
  ProjectListItem,
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
};

export function useMyProjects() {
  return useQuery({
    queryKey: keys.list,
    queryFn: () => api<ProjectListItem[]>("/projects"),
  });
}

export function useProject(id: string) {
  return useQuery({
    queryKey: keys.project(id),
    queryFn: () => api<Project>(`/projects/${id}`),
  });
}

export function useProjectSlots(id: string) {
  return useQuery({
    queryKey: keys.slots(id),
    queryFn: () => api<Slot[]>(`/projects/${id}/slots`),
  });
}

export function useProjectMilestones(id: string) {
  return useQuery({
    queryKey: keys.milestones(id),
    queryFn: () => api<Milestone[]>(`/projects/${id}/milestones`),
  });
}

export function useProjectDependencies(id: string) {
  return useQuery({
    queryKey: keys.dependencies(id),
    queryFn: () => api<Dependency[]>(`/projects/${id}/dependencies`),
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

/** Patch a DRAFT; sends the current version via If-Match so stale saves 409. */
export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({ body, version }: { body: ProjectUpdate; version: number }) =>
      api<Project>(`/projects/${id}`, {
        method: "PATCH",
        body,
        headers: { "If-Match": String(version) },
      }),
    onSuccess: (project) => {
      qc.setQueryData(keys.project(id), project);
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

export function useReplaceSlots(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (slots: SlotIn[]) =>
      api<Slot[]>(`/projects/${id}/slots`, { method: "PUT", body: { slots } }),
    onSuccess: (slots) => {
      qc.setQueryData(keys.slots(id), slots);
      void qc.invalidateQueries({ queryKey: keys.project(id) });
    },
  });
}

export function useReplaceMilestones(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (milestones: MilestoneIn[]) =>
      api<Milestone[]>(`/projects/${id}/milestones`, { method: "PUT", body: { milestones } }),
    onSuccess: (milestones) => qc.setQueryData(keys.milestones(id), milestones),
  });
}

export function useReplaceDependencies(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (dependencies: Dependency[]) =>
      api<Dependency[]>(`/projects/${id}/dependencies`, {
        method: "PUT",
        body: { dependencies },
      }),
    onSuccess: (deps) => qc.setQueryData(keys.dependencies(id), deps),
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
