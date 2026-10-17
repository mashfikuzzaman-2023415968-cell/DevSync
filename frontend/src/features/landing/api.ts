import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

/** Live platform numbers (spec §13.11 #3). Each field is present only once the phase that
 * produces it exists; absent or zero values are never shown. */
export interface PublicStats {
  developers?: number | null;
  clients?: number | null;
  projects_planned?: number | null;
  newcomers_hired?: number | null;
  on_time_rate?: number | null;
}

export function usePublicStats() {
  return useQuery({
    queryKey: ["public-stats"],
    staleTime: 5 * 60_000,
    queryFn: () => api<PublicStats>("/public/stats"),
  });
}
