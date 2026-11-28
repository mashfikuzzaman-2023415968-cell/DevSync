/** In-app notifications (spec §10.2 Notifications, §12; D122, D153, D162).
 *
 * - The list and the bell's count; the count is also re-read when the window gets focus and
 *   every 60 s while the page is visible (the fallback when the live stream can't connect).
 * - `useNotificationStream`: Server-Sent Events from `/notifications/stream`. Each event only
 *   says something new arrived ({id, type, title}); the list and count are then re-read. The
 *   browser reconnects by itself (with `Last-Event-ID`) when a stream ends; if it gives up
 *   (refused, offline), it is tried again with a growing pause, up to a minute.
 * - Preferences: one switch pair per §12 row, saved as soon as it changes. */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, API_BASE } from "@/api/client";
import type {
  NotificationItem,
  NotificationPage,
  NotificationPreferences,
  PreferenceItem,
} from "@/api/types";

export const keys = {
  list: ["notifications", "list"] as const,
  unread: ["notifications", "unread"] as const,
  preferences: ["notification-preferences"] as const,
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

/** Pauses before trying a refused or broken stream again (ms). */
export const STREAM_BACKOFF = [2_000, 5_000, 15_000, 30_000, 60_000] as const;

/** Keep the list and the bell live while signed in. Without EventSource (tests, old browsers)
 * nothing happens and the 60 s refresh carries on. */
export function useNotificationStream(enabled: boolean) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    let source: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let failures = 0;
    let stopped = false;
    const open = () => {
      if (stopped) return;
      source = new EventSource(`${API_BASE}/notifications/stream`);
      source.addEventListener("open", () => {
        failures = 0;
      });
      source.addEventListener("notification", () => {
        void qc.invalidateQueries({ queryKey: ["notifications"] });
      });
      source.addEventListener("error", () => {
        // CONNECTING: the browser retries by itself. CLOSED: it gave up; try again later.
        if (source?.readyState !== EventSource.CLOSED) return;
        source.close();
        const pause = STREAM_BACKOFF[Math.min(failures, STREAM_BACKOFF.length - 1)];
        failures += 1;
        timer = setTimeout(open, pause);
      });
    };
    open();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      source?.close();
    };
  }, [enabled, qc]);
}

export function useNotificationPreferences() {
  return useQuery({
    queryKey: keys.preferences,
    queryFn: () => api<NotificationPreferences>("/notification-preferences"),
  });
}

/** Save one row's switches; the switch moves at once and moves back if the save fails. */
export function useSavePreference() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (item: Pick<PreferenceItem, "category" | "in_app" | "email">) =>
      api<NotificationPreferences>("/notification-preferences", {
        method: "PUT",
        body: { items: [item] },
      }),
    onMutate: async (item) => {
      await qc.cancelQueries({ queryKey: keys.preferences });
      const before = qc.getQueryData<NotificationPreferences>(keys.preferences);
      qc.setQueryData<NotificationPreferences>(keys.preferences, (d) =>
        d
          ? {
              items: d.items.map((i) =>
                i.category === item.category ? { ...i, in_app: item.in_app, email: item.email } : i,
              ),
            }
          : d,
      );
      return { before };
    },
    onError: (_e, _item, ctx) => {
      if (ctx?.before) qc.setQueryData(keys.preferences, ctx.before);
    },
    onSuccess: (saved) => {
      qc.setQueryData(keys.preferences, saved);
    },
  });
}
