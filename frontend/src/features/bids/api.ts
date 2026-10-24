/** Sealed-bid data hooks (spec §10 Bids). My bids are cursor-paged (§10.1); edits and
 * withdrawals send the bid's `version` as `If-Match`, so a change made in another tab is a 409
 * `VERSION_CONFLICT` instead of being overwritten. */
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  Bid,
  BidCreate,
  BidDetail,
  BidPage,
  BidUpdate,
  ClientBids,
  EligibilityIn,
  EligibilityOut,
  TermsChange,
  TermsPreview,
} from "@/api/types";

export const keys = {
  mine: ["me", "bids"] as const,
  mineForProject: (projectId: string) => ["me", "bids", "project", projectId] as const,
  detail: (bidId: string) => ["me", "bids", "detail", bidId] as const,
  clientBids: (projectId: string) => ["projects", projectId, "bids"] as const,
};

/** After placing, changing or withdrawing a bid: my bids, plus the recommendations (the server
 * drops a project you've bid on from them; a withdrawn one may come back). */
function afterBidChange(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: keys.mine }),
    qc.invalidateQueries({ queryKey: ["projects", "recommended"] }),
  ]);
}

function bidsPath(params: {
  cursor?: string | null;
  projectId?: string;
  status?: string;
  limit?: number;
}) {
  const p = new URLSearchParams();
  if (params.projectId) p.set("project_id", params.projectId);
  if (params.status) p.set("status", params.status);
  if (params.limit) p.set("limit", String(params.limit));
  if (params.cursor) p.set("cursor", params.cursor);
  const qs = p.toString();
  return `/me/bids${qs ? `?${qs}` : ""}`;
}

/** All my bids, newest first, a page at a time ("Load more"). */
export function useMyBids() {
  return useInfiniteQuery({
    queryKey: keys.mine,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => api<BidPage>(bidsPath({ cursor: pageParam })),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

/** My newest few bids (the dashboard's "Recent bids"). */
export function useRecentBids(limit: number) {
  return useQuery({
    queryKey: [...keys.mine, "recent", limit] as const,
    queryFn: () => api<BidPage>(bidsPath({ limit })),
  });
}

/** My open (ACTIVE) bids: at most 30 by the server's cap, so one page of 100 holds them all. */
export function useOpenBids() {
  return useQuery({
    queryKey: [...keys.mine, "open"] as const,
    queryFn: () => api<BidPage>(bidsPath({ status: "ACTIVE", limit: 100 })),
  });
}

/** My bids on one project (at most one is standing; older ones are withdrawn). */
export function useMyBidsOnProject(projectId: string) {
  return useQuery({
    queryKey: keys.mineForProject(projectId),
    queryFn: () => api<BidPage>(bidsPath({ projectId, limit: 100 })),
    enabled: Boolean(projectId),
  });
}

/** One of my bids with its project and what I can still do (`/dev/bids/:id`). */
export function useBid(bidId: string) {
  return useQuery({
    queryKey: keys.detail(bidId),
    queryFn: () => api<BidDetail>(`/bids/${bidId}`),
    enabled: Boolean(bidId),
  });
}

export function useCreateBid(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: BidCreate) =>
      api<Bid>(`/projects/${projectId}/bids`, { method: "POST", body }),
    onSuccess: () => afterBidChange(qc),
  });
}

export function useUpdateBid() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({ bidId, body, version }: { bidId: string; body: BidUpdate; version: number }) =>
      api<Bid>(`/bids/${bidId}`, {
        method: "PATCH",
        body,
        headers: { "If-Match": String(version) },
      }),
    onSuccess: () => afterBidChange(qc),
  });
}

export function useWithdrawBid() {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: ({ bidId, version }: { bidId: string; version: number }) =>
      api<undefined>(`/bids/${bidId}`, {
        method: "DELETE",
        headers: { "If-Match": String(version) },
      }),
    onSettled: () => afterBidChange(qc),
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
