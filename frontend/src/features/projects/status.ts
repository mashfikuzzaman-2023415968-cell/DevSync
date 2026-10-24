/** Project status labels, tones and groups shared by My projects and the client dashboard. */
import type { Tone } from "@/components/ui/Display";

export const PROJECT_STATUS_TONE: Record<string, Tone> = {
  DRAFT: "neutral",
  BIDDING: "info",
  FORMING: "info",
  TEAM_PENDING: "warning",
  IN_PROGRESS: "primary",
  ON_HOLD: "warning",
  REVIEW_WINDOW: "warning",
  COMPLETED: "success",
  CANCELLED: "danger",
};

/** "IN_PROGRESS" → "In progress" (the badge text). */
export function projectStatusLabel(status: string): string {
  return status.charAt(0) + status.slice(1).toLowerCase().replace(/_/g, " ");
}

const STATUS_WORDS: Record<string, string> = {
  DRAFT: "Saved as a draft",
  BIDDING: "Open for bids",
  FORMING: "Forming a team",
  TEAM_PENDING: "Waiting for the team to accept",
  IN_PROGRESS: "Work in progress",
  ON_HOLD: "On hold",
  REVIEW_WINDOW: "In the review window",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
};

/** The status as a short phrase for activity feeds. */
export function projectStatusWords(status: string): string {
  return STATUS_WORDS[status] ?? projectStatusLabel(status);
}

/** Statuses counted as "active" on the client dashboard (spec §13.5 #20). */
export const ACTIVE_STATUSES: ReadonlySet<string> = new Set([
  "FORMING",
  "TEAM_PENDING",
  "IN_PROGRESS",
  "ON_HOLD",
  "REVIEW_WINDOW",
]);

/** The next thing a client does with a project, and where. */
export function projectNextAction(p: { id: string; status: string }): {
  label: string;
  to: string;
} {
  if (p.status === "DRAFT") {
    return { label: "Continue editing", to: `/client/projects/new?draft=${p.id}` };
  }
  if (p.status === "BIDDING" || p.status === "FORMING") {
    return { label: "See bids", to: `/client/projects/${p.id}/bids` };
  }
  return { label: "View plan", to: `/client/projects/${p.id}/plan` };
}
