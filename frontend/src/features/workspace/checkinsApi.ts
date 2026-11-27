/** Weekly check-in hooks (spec §10.2 Check-ins; D145): the feed, newest week first, 20 at a time
 * with "Show more", and posting this week's check-in. */
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Checkin, CheckinCreate, CheckinFeed } from "@/api/types";

export const checkinKeys = {
  feed: (projectId: string) => ["projects", projectId, "checkins"] as const,
};

export function useCheckins(projectId: string) {
  return useInfiniteQuery({
    queryKey: checkinKeys.feed(projectId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api<CheckinFeed>(
        `/projects/${projectId}/checkins${pageParam ? `?cursor=${encodeURIComponent(pageParam)}` : ""}`,
      ),
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: 30_000,
  });
}

export function usePostCheckin(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: CheckinCreate) =>
      api<Checkin>(`/projects/${projectId}/checkins`, { method: "POST", body }),
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: checkinKeys.feed(projectId) }),
        qc.invalidateQueries({ queryKey: ["projects", projectId, "dashboard"] }),
      ]),
  });
}

/** Feed items grouped by week, newest week first, keeping the server's order inside a week. */
export function byWeek(items: Checkin[]): { week: string; items: Checkin[] }[] {
  const groups: { week: string; items: Checkin[] }[] = [];
  for (const item of items) {
    const last = groups.at(-1);
    if (last && last.week === item.week_start) last.items.push(item);
    else groups.push({ week: item.week_start, items: [item] });
  }
  return groups;
}
