/**
 * Client error reports (spec §15.7): the error boundary sends a short, sanitized summary to
 * `/api/v1/client-errors` (rate-limited and sanitized again on the server). Only the path is
 * sent (never query strings, which can hold tokens), messages and stacks are truncated, and at
 * most a few reports leave one page view.
 */
import { api } from "@/api/client";

const MAX_REPORTS = 5;
let sent = 0;

export interface ClientErrorReport {
  message: string;
  stack: string | null;
  path: string;
  kind: "render" | "chunk" | "unhandled";
  request_id: string | null;
}

export function summarize(error: unknown, kind: ClientErrorReport["kind"]): ClientErrorReport {
  const err = error instanceof Error ? error : new Error(String(error));
  const requestId =
    typeof (error as { requestId?: unknown }).requestId === "string"
      ? (error as { requestId: string }).requestId
      : null;
  return {
    message: `${err.name}: ${err.message}`.slice(0, 500),
    stack: err.stack ? err.stack.slice(0, 4000) : null,
    path: window.location.pathname.slice(0, 300),
    kind,
    request_id: requestId,
  };
}

export async function reportClientError(
  error: unknown,
  kind: ClientErrorReport["kind"] = "render",
): Promise<void> {
  if (sent >= MAX_REPORTS) return;
  sent += 1;
  try {
    await api<undefined>("/client-errors", { method: "POST", body: summarize(error, kind) });
  } catch {
    // Reporting must never cause another visible error.
  }
}

/** Test hook. */
export function resetReportBudget(): void {
  sent = 0;
}
