/** Team formation data hooks (spec §10.2 Formation, §10.3). Starting a run is a 202 with a job;
 * `useJobProgress` follows the job's Server-Sent Events stream (same origin, the session cookie
 * rides along) and the run is re-read when it finishes. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { API_BASE, api } from "@/api/client";
import type {
  BidExplanationOut,
  ConfirmTeam,
  FormationRun,
  FormationRunAccepted,
  FormationRunCreate,
  FormationRunSummary,
} from "@/api/types";

export const keys = {
  runs: (projectId: string) => ["projects", projectId, "formation-runs"] as const,
  run: (runId: string) => ["formation-runs", runId] as const,
  explanation: (bidId: string) => ["me", "bids", "explanation", bidId] as const,
};

const ACTIVE = new Set(["QUEUED", "RUNNING"]);

export function useFormationRuns(projectId: string) {
  return useQuery({
    queryKey: keys.runs(projectId),
    queryFn: () => api<FormationRunSummary[]>(`/projects/${projectId}/formation-runs`),
  });
}

/** One run; while it is queued or running it is re-read every 3 s as a fallback for SSE. */
export function useFormationRun(runId: string | null) {
  return useQuery({
    queryKey: keys.run(runId ?? ""),
    enabled: Boolean(runId),
    queryFn: () => api<FormationRun>(`/formation-runs/${runId ?? ""}`),
    refetchInterval: (q) => (q.state.data && ACTIVE.has(q.state.data.status) ? 3000 : false),
  });
}

export function useStartRun(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (body: FormationRunCreate) =>
      api<FormationRunAccepted>(`/projects/${projectId}/formation-runs`, {
        method: "POST",
        body,
        headers: { "Idempotency-Key": crypto.randomUUID() },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.runs(projectId) }),
  });
}

export function useConfirmTeam(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: (runId: string) =>
      api<ConfirmTeam>(`/formation-runs/${runId}/confirm`, { method: "POST" }),
    onSuccess: (_data, runId) =>
      Promise.all([
        qc.invalidateQueries({ queryKey: keys.runs(projectId) }),
        qc.invalidateQueries({ queryKey: keys.run(runId) }),
        qc.invalidateQueries({ queryKey: ["projects", projectId] }),
      ]),
  });
}

/** Why my bid was not selected; 404 means there is nothing to explain (yet). */
export function useBidExplanation(bidId: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.explanation(bidId),
    enabled,
    retry: false,
    queryFn: () => api<BidExplanationOut>(`/bids/${bidId}/explanation`),
  });
}

export interface JobProgress {
  progress: number;
  iteration: number | null;
  /** Best fitness so far, one value per progress event (the live convergence line). */
  best: number[];
  status: string | null;
}

const EMPTY: JobProgress = { progress: 0, iteration: null, best: [], status: null };

function parse(data: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(data);
    return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** Live progress of a job over SSE; stops at the final status. Without EventSource (tests,
 * old browsers) it stays empty and the run's polling takes over. */
export function useJobProgress(jobId: string | null, onDone?: () => void): JobProgress {
  const [state, setState] = useState<JobProgress>(EMPTY);
  useEffect(() => {
    setState(EMPTY);
    if (!jobId || typeof EventSource === "undefined") return;
    const source = new EventSource(`${API_BASE}/jobs/${jobId}/events`);
    const handle = (event: MessageEvent<string>) => {
      const e = parse(event.data);
      if (!e) return;
      const status = typeof e.status === "string" ? e.status : null;
      setState((s) => ({
        progress: typeof e.progress === "number" ? e.progress : s.progress,
        iteration: typeof e.iteration === "number" ? e.iteration : s.iteration,
        best: typeof e.best_fitness === "number" ? [...s.best, e.best_fitness] : s.best,
        status: status ?? s.status,
      }));
      if (status && !ACTIVE.has(status)) {
        source.close();
        onDone?.();
      }
    };
    source.addEventListener("progress", handle);
    source.addEventListener("status", handle);
    return () => {
      source.close();
    };
    // onDone is a callback; re-subscribing when it changes would restart the stream.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);
  return state;
}
