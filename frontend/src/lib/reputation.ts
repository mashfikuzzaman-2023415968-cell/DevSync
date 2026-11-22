/** Plain-language names for the reputation model (spec §13.5 #16, §13.10).
 *
 * Users see these labels, never ω, X_m or "Eq. 11". The paper symbols appear only in the
 * "How it’s calculated" drawer, next to the plain label. */
import type { ReputationParameters } from "@/api/types";

export type ParameterKey = keyof ReputationParameters;

export interface ParameterInfo {
  key: ParameterKey;
  label: string;
  symbol: string;
  /** What it measures, in one sentence. */
  means: string;
  /** What raises it, in one sentence. */
  grows: string;
}

export const PARAMETERS: readonly ParameterInfo[] = [
  {
    key: "omega",
    label: "Expertise",
    symbol: "ω",
    means:
      "How varied your completed projects are: work across several areas counts more than many projects in one.",
    grows:
      "Completing a project in a new area. While you’re a newcomer, a passed role assessment counts too.",
  },
  {
    key: "x",
    label: "Communication",
    symbol: "X",
    means:
      "How well you keep clients and teammates informed: on-time check-ins, quick replies and accurate updates.",
    grows:
      "Posting weekly check-ins on time and replying within a day when someone asks you something.",
  },
  {
    key: "xm",
    label: "Teamwork",
    symbol: "Xₘ",
    means:
      "How your teammates rate working with you, and how often you help them with blockers and reviews.",
    grows: "Answering teammates’ blockers and reviewing their work.",
  },
  {
    key: "beta",
    label: "Quality",
    symbol: "β",
    means:
      "What clients thought of your work, milestone by milestone, plus verified reviews from outside DevSync.",
    grows:
      "Milestones approved with good ratings. Older projects weigh a little more, so one project never swings it far.",
  },
  {
    key: "mu",
    label: "Client diversity",
    symbol: "μ",
    means: "Whether different clients choose to hire you, rather than one client again and again.",
    grows: "Completing projects for new clients.",
  },
  {
    key: "t",
    label: "Punctuality",
    symbol: "T",
    means:
      "How much time you leave before the deadline: finishing sooner gives a higher score, and late work scores 0 for that project.",
    grows: "Finishing your part before the project’s deadline.",
  },
];

export const PARAMETER_BY_KEY: Record<ParameterKey, ParameterInfo> = Object.fromEntries(
  PARAMETERS.map((p) => [p.key, p]),
) as Record<ParameterKey, ParameterInfo>;

/** Which parameters make up competency (C) and performance (P), for grouping on screen. */
export const COMPETENCY_PARTS: readonly ParameterKey[] = ["omega", "x"];
export const PERFORMANCE_PARTS: readonly ParameterKey[] = ["beta", "mu", "t"];

/** A 0–1 decimal string from the API as a number, or null. */
export function toNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

const DOMAIN_WORDS: Record<string, string> = {
  FRONTEND: "Front-end",
  BACKEND: "Back-end",
  DATABASE: "Database",
  MOBILE: "Mobile",
  DESIGN: "Design",
  TESTING: "Testing",
  DEVOPS: "DevOps",
  DATA: "Data",
};

export function domainLabel(domain: string): string {
  return DOMAIN_WORDS[domain] ?? domain;
}
