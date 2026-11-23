/** Team lifecycle hooks (spec §10.2 Team; D118–D138). Every action invalidates the team, the
 * repair and the dashboards' lists, so each screen shows the new state at once. */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  ActionResult,
  ClientTeamCard,
  LeadChangeRequest,
  MyInvitations,
  RepairOut,
  TeamView,
} from "@/api/types";

export const keys = {
  team: (projectId: string) => ["projects", projectId, "team"] as const,
  repair: (projectId: string) => ["projects", projectId, "repair"] as const,
  myInvitations: ["me", "invitations"] as const,
  myTeams: ["me", "teams"] as const,
};

function refresh(qc: QueryClient, projectId?: string) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: keys.myInvitations }),
    qc.invalidateQueries({ queryKey: keys.myTeams }),
    qc.invalidateQueries({ queryKey: ["notifications"] }),
    ...(projectId
      ? [
          qc.invalidateQueries({ queryKey: keys.team(projectId) }),
          qc.invalidateQueries({ queryKey: keys.repair(projectId) }),
          qc.invalidateQueries({ queryKey: ["projects", projectId] }),
        ]
      : []),
  ]);
}

export function useTeam(projectId: string) {
  return useQuery({
    queryKey: keys.team(projectId),
    queryFn: () => api<TeamView>(`/projects/${projectId}/team`),
    retry: false,
  });
}

/** The latest repair proposal; re-read every 3 s while it is computing. */
export function useRepair(projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.repair(projectId),
    enabled,
    retry: false,
    queryFn: () => api<RepairOut>(`/projects/${projectId}/repair`),
    refetchInterval: (q) => (q.state.data?.status === "COMPUTING" ? 3000 : false),
  });
}

export function useMyInvitations(enabled = true) {
  return useQuery({
    queryKey: keys.myInvitations,
    enabled,
    queryFn: () => api<MyInvitations>("/me/invitations"),
  });
}

export function useMyTeams() {
  return useQuery({ queryKey: keys.myTeams, queryFn: () => api<ClientTeamCard[]>("/me/teams") });
}

function action<T>(
  qc: QueryClient,
  projectId: string | undefined,
  fn: (vars: T) => Promise<unknown>,
) {
  return {
    meta: { inlineErrors: true },
    mutationFn: fn,
    onSuccess: () => refresh(qc, projectId),
  };
}

export function useAnswerInvitation(projectId?: string) {
  const qc = useQueryClient();
  return useMutation(
    action(
      qc,
      projectId,
      ({ id, accept, reason }: { id: string; accept: boolean; reason?: string | undefined }) =>
        api<ActionResult>(`/invitations/${id}/${accept ? "accept" : "decline"}`, {
          method: "POST",
          ...(accept ? {} : { body: reason ? { reason } : {} }),
        }),
    ),
  );
}

export function useChooseLead(projectId: string) {
  const qc = useQueryClient();
  return useMutation(
    action(qc, projectId, (v: { memberId: string; version: number; reason?: string }) =>
      api<ActionResult>(`/projects/${projectId}/team/lead`, {
        method: "POST",
        headers: { "If-Match": String(v.version) },
        body: v.reason ? { member_id: v.memberId, reason: v.reason } : { member_id: v.memberId },
      }),
    ),
  );
}

export function useDeclineLead(projectId: string) {
  const qc = useQueryClient();
  return useMutation(
    action(qc, projectId, () =>
      api<ActionResult>(`/projects/${projectId}/team/lead/decline`, { method: "POST" }),
    ),
  );
}

export function useStartProject(projectId: string) {
  const qc = useQueryClient();
  return useMutation(
    action(qc, projectId, (version: number) =>
      api<ActionResult>(`/projects/${projectId}/start`, {
        method: "POST",
        headers: { "If-Match": String(version) },
      }),
    ),
  );
}

export function useRequestLeadChange(projectId: string) {
  const qc = useQueryClient();
  return useMutation(
    action(qc, projectId, (body: { reason: string; suggested_member_id?: string }) =>
      api<LeadChangeRequest>(`/projects/${projectId}/lead-change-requests`, {
        method: "POST",
        body,
      }),
    ),
  );
}

export function useDecideLeadChange(projectId: string) {
  const qc = useQueryClient();
  return useMutation(
    action(
      qc,
      projectId,
      (v: { id: string; verb: "approve" | "reject" | "withdraw"; reason?: string }) =>
        api<ActionResult>(`/lead-change-requests/${v.id}/${v.verb}`, {
          method: "POST",
          ...(v.verb === "reject" ? { body: { reason: v.reason ?? "" } } : {}),
        }),
    ),
  );
}

export function useLeave(projectId: string) {
  const qc = useQueryClient();
  return useMutation(
    action(qc, projectId, (v: { memberId: string; reason: string }) =>
      api<ActionResult>(`/team-members/${v.memberId}/leave`, {
        method: "POST",
        body: { reason: v.reason },
      }),
    ),
  );
}

export function useChooseReplacement(projectId: string) {
  const qc = useQueryClient();
  return useMutation(
    action(qc, projectId, (v: { proposalId: string; bidId: string }) =>
      api<RepairOut>(`/repair-proposals/${v.proposalId}/choose`, {
        method: "POST",
        body: { bid_id: v.bidId },
      }),
    ),
  );
}

export function useReopenSlot(projectId: string) {
  const qc = useQueryClient();
  return useMutation(
    action(qc, projectId, (slotId: string) =>
      api<RepairOut>(`/projects/${projectId}/slots/${slotId}/reopen`, { method: "POST" }),
    ),
  );
}

export function useRaiseBudget(projectId: string) {
  const qc = useQueryClient();
  return useMutation(
    action(qc, projectId, (v: { budgetPaisa: number; version: number }) =>
      api<RepairOut>(`/projects/${projectId}/budget`, {
        method: "POST",
        headers: { "If-Match": String(v.version) },
        body: { budget_paisa: v.budgetPaisa },
      }),
    ),
  );
}
