/** Monitoring hooks (spec §10.2 Monitoring, §13.7; D151, D152): the dashboard refetches on focus,
 * lists keep 30 s; the plan (with its forecast) comes from the projects feature. */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { ActivityPage, Dashboard, EvidenceSummary, RiskList } from "@/api/types";

export const monitoringKeys = {
  dashboard: (projectId: string) => ["projects", projectId, "dashboard"] as const,
  risks: (projectId: string) => ["projects", projectId, "risks"] as const,
  activity: (projectId: string) => ["projects", projectId, "activity"] as const,
  evidence: (projectId: string) => ["projects", projectId, "evidence"] as const,
};

export function useDashboard(projectId: string) {
  return useQuery({
    queryKey: monitoringKeys.dashboard(projectId),
    queryFn: () => api<Dashboard>(`/projects/${projectId}/dashboard`),
    refetchOnWindowFocus: true,
    retry: false,
  });
}

export function useRisks(projectId: string) {
  return useQuery({
    queryKey: monitoringKeys.risks(projectId),
    queryFn: () => api<RiskList>(`/projects/${projectId}/risks`),
    staleTime: 30_000,
  });
}

export function useActivity(projectId: string, pageSize = 20) {
  return useInfiniteQuery({
    queryKey: [...monitoringKeys.activity(projectId), pageSize],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const q = new URLSearchParams({ limit: String(pageSize) });
      if (pageParam) q.set("cursor", pageParam);
      return api<ActivityPage>(`/projects/${projectId}/activity?${q.toString()}`);
    },
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: 30_000,
  });
}

export function useEvidence(projectId: string) {
  return useQuery({
    queryKey: monitoringKeys.evidence(projectId),
    queryFn: () => api<EvidenceSummary>(`/projects/${projectId}/evidence`),
    staleTime: 30_000,
  });
}

/** Plain words for the risk actions the engine suggests (§13.5 #39). */
export const ACTION_LABEL: Record<string, string> = {
  REPLAN: "Re-plan on the Timeline",
  MESSAGE_TEAM: "Discuss with the team",
  MESSAGE_MEMBER: "Message the member",
  FIND_REPLACEMENT: "Request removal or a replacement",
  REASSIGN: "Reassign tasks",
  REVIEW_BUDGET: "Review the budget",
  ADD_FUNDS: "Add funds",
  REVIEW_SUBMISSION: "Review the submission",
};

export const HEALTH_LABEL: Record<string, string> = {
  HEALTHY: "Healthy",
  AT_RISK: "At risk",
  CRITICAL: "Critical",
};
