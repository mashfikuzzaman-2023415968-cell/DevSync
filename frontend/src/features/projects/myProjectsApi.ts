/** A developer's own projects (spec §13.5 #13, #9): `GET /me/projects`, active or completed,
 * 20 at a time with "Show more". Progress and risk are the member-shaped dashboard's numbers. */
import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { MyProjectPage } from "@/api/types";

export type MyProjectsState = "active" | "completed";

export const myProjectKeys = {
  list: (state: MyProjectsState) => ["me", "projects", state] as const,
};

export function useMyProjects(state: MyProjectsState, enabled = true) {
  return useInfiniteQuery({
    queryKey: myProjectKeys.list(state),
    enabled,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const q = new URLSearchParams({ state });
      if (pageParam) q.set("cursor", pageParam);
      return api<MyProjectPage>(`/me/projects?${q.toString()}`);
    },
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: 30_000,
  });
}
