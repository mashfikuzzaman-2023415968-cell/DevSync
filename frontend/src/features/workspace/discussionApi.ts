/** Discussion thread hooks (spec §10.2 Discussion; D146): the project's threads, most recently
 * active first, 20 at a time with "Show more" (refreshed with the open thread's polling), and
 * starting a thread with its first post. Posts use the comment hooks (`DISCUSSION_POST`). */
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Thread, ThreadCreate, ThreadPage } from "@/api/types";
import { DISCUSSION_POLL_MS } from "./commentsApi";

export const threadKeys = {
  list: (projectId: string) => ["threads", projectId] as const,
};

export function useThreads(projectId: string) {
  return useInfiniteQuery({
    queryKey: threadKeys.list(projectId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api<ThreadPage>(
        `/projects/${projectId}/threads${pageParam ? `?cursor=${encodeURIComponent(pageParam)}` : ""}`,
      ),
    getNextPageParam: (last) => last.next_cursor ?? null,
    refetchInterval: DISCUSSION_POLL_MS,
  });
}

export function useCreateThread(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: ThreadCreate) =>
      api<Thread>(`/projects/${projectId}/threads`, { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: threadKeys.list(projectId) }),
  });
}
