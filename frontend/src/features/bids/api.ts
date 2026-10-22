/** Sealed-bid data hooks (spec §10 Bids). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  Bid,
  BidCreate,
  BidUpdate,
  ClientBids,
  EligibilityIn,
  EligibilityOut,
  TermsChange,
  TermsPreview,
} from "@/api/types";

export const keys = {
  mine: ["me", "bids"] as const,
  clientBids: (projectId: string) => ["projects", projectId, "bids"] as const,
};

export function useMyBids() {
  return useQuery({ queryKey: keys.mine, queryFn: () => api<Bid[]>("/me/bids") });
}

export function useCreateBid(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: BidCreate) =>
      api<Bid>(`/projects/${projectId}/bids`, { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.mine }),
  });
}

export function useUpdateBid() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({ bidId, body }: { bidId: string; body: BidUpdate }) =>
      api<Bid>(`/bids/${bidId}`, { method: "PATCH", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.mine }),
  });
}

export function useWithdrawBid() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (bidId: string) => api<undefined>(`/bids/${bidId}`, { method: "DELETE" }),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.mine }),
  });
}

/** Dry-run eligibility for the bid sheet's live preview (not persisted). */
export function useEligibilityPreview(projectId: string) {
  return useMutation({
    mutationFn: (body: EligibilityIn) =>
      api<EligibilityOut>(`/projects/${projectId}/bids/eligibility`, { method: "POST", body }),
  });
}

export function useClientBids(projectId: string) {
  return useQuery({
    queryKey: keys.clientBids(projectId),
    queryFn: () => api<ClientBids>(`/projects/${projectId}/bids`),
  });
}

/** What a too-few-bids action would do (§9.19) — nothing is saved. */
export function useTermsPreview(projectId: string) {
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: TermsChange) =>
      api<TermsPreview>(`/projects/${projectId}/bidding-terms/preview`, { method: "POST", body }),
  });
}

/** Lower the standards, raise the budget or reduce the team; returns the fresh bids view. */
export function useChangeTerms(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: TermsChange) =>
      api<ClientBids>(`/projects/${projectId}/bidding-terms`, { method: "PATCH", body }),
    onSuccess: (view) => {
      qc.setQueryData(keys.clientBids(projectId), view);
      void qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
