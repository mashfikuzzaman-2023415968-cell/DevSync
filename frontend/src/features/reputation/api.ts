/** Reputation data hooks (spec §10.2 Reputation). Both are reads: the server computes
 * reputation from evidence; nothing here writes it. */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { DeveloperReputation, ReputationHistoryPage } from "@/api/types";

export const keys = {
  developer: (id: string) => ["developers", id, "reputation"] as const,
  history: ["me", "reputation", "history"] as const,
};

/** A developer's reputation (any signed-in user; hidden profiles are a 404). */
export function useDeveloperReputation(id: string | undefined) {
  return useQuery({
    queryKey: keys.developer(id ?? ""),
    queryFn: () =>
      api<DeveloperReputation>(`/developers/${encodeURIComponent(id ?? "")}/reputation`),
    enabled: Boolean(id),
  });
}

/** How my reputation changed, newest project first. One page of up to 100 projects is enough
 * for the trend chart; older ones are summarised by the snapshot itself. */
export function useMyReputationHistory() {
  return useQuery({
    queryKey: keys.history,
    queryFn: () => api<ReputationHistoryPage>("/me/reputation/history?limit=100"),
  });
}
