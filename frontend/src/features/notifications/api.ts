/** In-app notifications (spec §10.2 Notifications; D122). The bell's count is re-read when the
 * window gets focus and every 60 s while the page is visible; the live stream is Phase 9. */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { NotificationItem, NotificationPage } from "@/api/types";

export const keys = {
  list: ["notifications", "list"] as const,
  unread: ["notifications", "unread"] as const,
};

export function useNotifications() {
  return useInfiniteQuery({
    queryKey: keys.list,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api<NotificationPage>(
        `/notifications${pageParam ? `?cursor=${encodeURIComponent(pageParam)}` : ""}`,
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useUnreadCount(enabled: boolean) {
  return useQuery({
    queryKey: keys.unread,
    enabled,
    queryFn: () => api<{ unread: number }>("/notifications/unread-count"),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });
}

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<NotificationItem>(`/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

export function useReadAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<{ marked: number }>("/notifications/read-all", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}
