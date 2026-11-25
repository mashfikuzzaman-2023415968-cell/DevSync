/** Plain words for team states (spec §13.10): statuses, invitation states, repair reasons. */
import type { Tone } from "@/components/ui/Display";

export const MEMBER_STATUS: Record<string, { label: string; tone: Tone }> = {
  INVITED: { label: "Invited", tone: "info" },
  ACTIVE: { label: "Accepted", tone: "success" },
  DECLINED: { label: "Declined", tone: "danger" },
  EXPIRED: { label: "Expired", tone: "warning" },
  COMPLETED: { label: "Completed", tone: "success" },
  LEFT: { label: "Left", tone: "neutral" },
  REMOVED: { label: "Removed", tone: "neutral" },
};

export const ATTENTION: Record<string, string> = {
  REPAIR_OPEN: "A place needs a replacement",
  INVITATION_EXPIRING: "An invitation expires soon",
  FULLY_BOOKED: "An invited developer is fully booked",
  CHOOSE_LEAD: "Choose a team lead",
};

/** 0–1 → 0–100 for display (§13.8). */
export function score(v: number): string {
  return String(Math.round(Math.min(1, Math.max(0, v)) * 100));
}

export function memberStatus(status: string): { label: string; tone: Tone } {
  return MEMBER_STATUS[status] ?? { label: status, tone: "neutral" };
}
