/**
 * Role assessment API (role assessment spec §9). The window token from start/resume is kept in
 * memory only (never in storage): every answer, leave and heartbeat sends it in
 * `X-Attempt-Token`, and a reload simply resumes, which issues a new one (§6.6).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  AssessmentAnswer,
  AssessmentAttempt,
  AssessmentResult,
  AssessmentStarted,
  AssessmentStatus,
  FocusEventResult,
  FocusEventType,
  HeartbeatResult,
  RoleAssessmentHistoryItem,
} from "@/api/types";

export const assessmentKeys = {
  status: (projectId: string, slotId: string) => ["assessment-status", projectId, slotId] as const,
  attempt: (id: string) => ["assessment-attempt", id] as const,
  history: ["role-assessments"] as const,
};

const tokens = new Map<string, string>();

export function attemptToken(attemptId: string): string | undefined {
  return tokens.get(attemptId);
}

export function forgetAttemptToken(attemptId: string): void {
  tokens.delete(attemptId);
}

function withToken(attemptId: string): Record<string, string> {
  const token = tokens.get(attemptId);
  return token ? { "X-Attempt-Token": token } : {};
}

/** An attempt with the server − browser clock difference measured when it arrived. */
export type TimedAssessment = AssessmentAttempt & { clock_offset_ms: number };

export function timedAssessment(attempt: AssessmentAttempt): TimedAssessment {
  return { ...attempt, clock_offset_ms: Date.parse(attempt.server_now) - Date.now() };
}

function remember(started: AssessmentStarted): TimedAssessment {
  const { attempt_token: token, ...attempt } = started;
  tokens.set(started.id, token);
  return timedAssessment(attempt);
}

export function useSlotAssessment(projectId: string, slotId: string, enabled = true) {
  return useQuery({
    queryKey: assessmentKeys.status(projectId, slotId),
    enabled: enabled && Boolean(projectId && slotId),
    refetchOnWindowFocus: true,
    queryFn: () => api<AssessmentStatus>(`/projects/${projectId}/slots/${slotId}/assessment`),
  });
}

export function useStartAssessment(projectId: string, slotId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: async (body: { consent: boolean; rules_version: number }) =>
      remember(
        await api<AssessmentStarted>(`/projects/${projectId}/slots/${slotId}/assessment/attempts`, {
          method: "POST",
          body,
          headers: { "Idempotency-Key": crypto.randomUUID() },
        }),
      ),
    onSuccess: (attempt) => {
      qc.setQueryData(assessmentKeys.attempt(attempt.id), attempt);
      void qc.invalidateQueries({ queryKey: assessmentKeys.status(projectId, slotId) });
    },
  });
}

/** A fresh window token for an attempt (reload, another device); the old window is moved. */
export async function resumeAttempt(attemptId: string): Promise<TimedAssessment> {
  return remember(
    await api<AssessmentStarted>(`/assessment-attempts/${attemptId}/resume`, { method: "POST" }),
  );
}

export function useResumeAttempt(attemptId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { inlineErrors: true },
    mutationFn: () => resumeAttempt(attemptId),
    onSuccess: (attempt) => {
      qc.setQueryData(assessmentKeys.attempt(attempt.id), attempt);
    },
  });
}

export function useAssessmentAttempt(attemptId: string) {
  return useQuery({
    queryKey: assessmentKeys.attempt(attemptId),
    enabled: Boolean(attemptId),
    retry: false,
    staleTime: Infinity,
    queryFn: async () =>
      timedAssessment(
        await api<AssessmentAttempt>(`/assessment-attempts/${attemptId}`, {
          headers: withToken(attemptId),
        }),
      ),
  });
}

export function answerQuestion(
  attemptId: string,
  body: { question_id: string; choice: number | null },
): Promise<AssessmentAnswer> {
  return api<AssessmentAnswer>(`/assessment-attempts/${attemptId}/answer`, {
    method: "POST",
    body,
    headers: withToken(attemptId),
  });
}

export function finishAttempt(attemptId: string): Promise<AssessmentResult> {
  return api<AssessmentResult>(`/assessment-attempts/${attemptId}/finish`, {
    method: "POST",
    headers: withToken(attemptId),
  });
}

export function sendFocusEvent(
  attemptId: string,
  body: { seq: number; type: FocusEventType; client_at: string; fullscreen_supported?: boolean },
  keepalive = false,
): Promise<FocusEventResult> {
  return api<FocusEventResult>(`/assessment-attempts/${attemptId}/focus-events`, {
    method: "POST",
    body,
    headers: withToken(attemptId),
    keepalive,
  });
}

export function sendHeartbeat(
  attemptId: string,
  body: { visible: boolean; fullscreen: boolean },
): Promise<HeartbeatResult> {
  return api<HeartbeatResult>(`/assessment-attempts/${attemptId}/heartbeat`, {
    method: "POST",
    body,
    headers: withToken(attemptId),
  });
}

export function useAssessmentResult(attemptId: string, enabled: boolean) {
  return useQuery({
    queryKey: [...assessmentKeys.attempt(attemptId), "result"],
    enabled: enabled && Boolean(attemptId),
    retry: false,
    queryFn: () => api<AssessmentResult>(`/assessment-attempts/${attemptId}/result`),
  });
}

export function useRoleAssessmentHistory() {
  return useQuery({
    queryKey: assessmentKeys.history,
    queryFn: () => api<RoleAssessmentHistoryItem[]>("/me/role-assessments"),
  });
}
