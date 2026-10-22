/** Human text for Algorithm 1 reason codes and checks (spec §9.2), shared by the bid views. */

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
