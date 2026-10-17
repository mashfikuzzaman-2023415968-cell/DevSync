import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { PublicStatsResponse } from "@/api/types";

/** Live platform numbers (spec §13.11 #3). The server sends a number only once the phase that
 * produces it exists (developers now; projects, newcomers hired and on-time rate later); absent
 * or zero values are never shown. */
export type PublicStats = PublicStatsResponse & {
  projects_planned?: number | null;
  newcomers_hired?: number | null;
  on_time_rate?: number | null;
};

export function usePublicStats() {
  return useQuery({
    queryKey: ["public-stats"],
    staleTime: 5 * 60_000,
    queryFn: () => api<PublicStats>("/public/stats"),
  });
}
