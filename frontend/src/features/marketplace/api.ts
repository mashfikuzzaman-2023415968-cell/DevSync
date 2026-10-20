/** Marketplace search, recommendations and the public project detail (spec §10, §9.16). */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { ProjectCardPage, ProjectDetail, RecommendedProject } from "@/api/types";

export interface SearchFilters {
  q?: string;
  skills?: string[];
  budget_min?: number | undefined;
  budget_max?: number | undefined;
  deadline_max?: number | undefined;
  team_size?: number | undefined;
  sort?: string;
}

const keys = {
  search: (f: SearchFilters) => ["projects", "search", f] as const,
  recommended: ["projects", "recommended"] as const,
  publicProject: (id: string) => ["public-project", id] as const,
};

/** Build a `/projects/search` query string from the filters and an optional cursor. */
function searchPath(f: SearchFilters, cursor: string | null): string {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  for (const s of f.skills ?? []) p.append("skills", s);
  if (f.budget_min != null) p.set("budget_min", String(f.budget_min));
  if (f.budget_max != null) p.set("budget_max", String(f.budget_max));
  if (f.deadline_max != null) p.set("deadline_max", String(f.deadline_max));
  if (f.team_size != null) p.set("team_size", String(f.team_size));
  if (f.sort) p.set("sort", f.sort);
  if (cursor) p.set("cursor", cursor);
  const qs = p.toString();
  return `/projects/search${qs ? `?${qs}` : ""}`;
}

export function useProjectSearch(filters: SearchFilters) {
  return useInfiniteQuery({
    queryKey: keys.search(filters),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => api<ProjectCardPage>(searchPath(filters, pageParam)),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useRecommended() {
  return useQuery({
    queryKey: keys.recommended,
    staleTime: 5 * 60_000,
    queryFn: () => api<RecommendedProject[]>("/projects/recommended"),
  });
}

/** A single open project with its slots, for the bid sheet (works for guests and developers). */
export function usePublicProject(id: string) {
  return useQuery({
    queryKey: keys.publicProject(id),
    queryFn: () => api<ProjectDetail>(`/public/projects/${id}`),
  });
}
