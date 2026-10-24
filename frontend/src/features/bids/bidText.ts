/** Human text for Algorithm 1 reason codes and checks (spec §9.2) and bid statuses, shared by
 * the bid views and the developer dashboard. */
import type { Tone } from "@/components/ui/Display";

export const BID_STATUS_TONE: Record<string, Tone> = {
  ACTIVE: "info",
  WITHDRAWN: "neutral",
  INELIGIBLE: "warning",
  SELECTED: "success",
  NOT_SELECTED: "neutral",
  ACCEPTED: "success",
  DECLINED: "danger",
  EXPIRED: "neutral",
};

/** Plain words where the code reads badly; the rest follow "NOT_SELECTED" → "Not selected". */
const STATUS_LABEL: Record<string, string> = {
  ACTIVE: "Open",
  INELIGIBLE: "Filtered out",
};

export function bidStatusLabel(status: string): string {
  return (
    STATUS_LABEL[status] ?? status.charAt(0) + status.slice(1).toLowerCase().replace(/_/g, " ")
  );
}

/** The bid's steps for the detail timeline (spec §13.5 #12): Submitted → Evaluated →
 * Selected / Not selected → Accepted. `done` steps are reached; `current` is where it stands. */
export interface BidStep {
  label: string;
  state: "done" | "current" | "upcoming" | "stopped";
  note?: string;
}

export function bidSteps(status: string, evaluated: boolean): BidStep[] {
  if (status === "WITHDRAWN") {
    return [
      { label: "Submitted", state: "done" },
      { label: "Withdrawn", state: "stopped", note: "You withdrew this bid." },
    ];
  }
  if (status === "INELIGIBLE") {
    return [
      { label: "Submitted", state: "done" },
      { label: "Evaluated", state: "stopped", note: "Filtered out when bidding closed." },
    ];
  }
  const selection: Record<string, BidStep> = {
    SELECTED: { label: "Selected", state: "current", note: "Respond to the invitation." },
    ACCEPTED: { label: "Selected", state: "done" },
    DECLINED: { label: "Selected", state: "done" },
    EXPIRED: { label: "Selected", state: "done" },
    NOT_SELECTED: { label: "Not selected", state: "stopped" },
  };
  const evaluatedStep: BidStep =
    evaluated || status in selection
      ? { label: "Evaluated", state: "done", note: "Meets the project’s requirements." }
      : { label: "Evaluated", state: "current", note: "Checked when bidding closes." };
  const last: BidStep =
    status === "ACCEPTED"
      ? { label: "Accepted", state: "done" }
      : status === "DECLINED"
        ? { label: "Declined", state: "stopped" }
        : status === "EXPIRED"
          ? { label: "Invitation expired", state: "stopped" }
          : { label: "Accepted", state: "upcoming" };
  return [
    { label: "Submitted", state: "done" },
    evaluatedStep,
    selection[status] ?? {
      label: "Selected or not selected",
      state: "upcoming",
      note: "Decided when the client forms the team.",
    },
    ...(status === "NOT_SELECTED" ? [] : [last]),
  ];
}

export const REASON_TEXT: Record<string, string> = {
  LOW_PERFORMANCE: "Performance below the minimum",
  LOW_COMPETENCY: "Competency below the minimum",
  TOO_SLOW: "Can’t meet the deadline",
  OVER_BUDGET: "Over budget",
  NO_SKILL_EVIDENCE: "No passing skill test",
  SKILL_MISMATCH: "Missing the slot’s skill",
  UNAVAILABLE: "Not enough free hours",
  SUSPENDED: "Account not active",
  SELF_DEALING: "Conflict of interest",
  NOT_SHORTLISTED: "Not in the top shortlist",
};

/** What each Algorithm 1 check tests, in the order the filter applies them. */
export const CHECK_LABEL: Record<string, string> = {
  account_active: "Account in good standing",
  has_slot_skill: "Lists the slot’s skill",
  no_conflict: "No conflict of interest",
  available: "Free hours over the project period",
  skill_evidence: "Newcomer rule: passing skill test",
  performance: "Performance at least the minimum",
  competency: "Competency at least the minimum",
  days: "Finishes within the deadline",
  price: "Price within the budget",
};

export function reasonText(reasons: readonly string[]): string {
  return reasons.map((r) => REASON_TEXT[r] ?? r).join(", ") || "Not eligible";
}
