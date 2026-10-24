/**
 * Find Projects filters (spec §13.5 #10) ↔ the URL query. The URL keeps what people type
 * (budgets in whole taka); `searchFilters` turns it into the API's query (budgets in paisa) and
 * leaves out anything invalid, so a hand-edited URL shows a field error instead of a 422.
 */
import { wholeIn } from "@/features/projects/schemas";
import type { SearchFilters } from "./api";

export const MAX_BUDGET_TAKA = 100_000_000;

/** URL keys the filter panel owns ("Clear filters" removes them; sort stays). */
export const FILTER_KEYS = [
  "q",
  "skills",
  "budget_min",
  "budget_max",
  "deadline_max",
  "role",
  "team_size",
  "hours",
] as const;

export interface ParsedFilters {
  /** The query for `/projects/search` (valid values only). */
  api: SearchFilters;
  /** Field problems keyed by URL key. */
  errors: Partial<Record<(typeof FILTER_KEYS)[number], string>>;
  /** Whether any filter is set (sort doesn't count). */
  active: boolean;
}

function whole(
  raw: string | null,
  min: number,
  max: number,
  message: string,
): { value?: number; error?: string } {
  if (raw === null || raw.trim() === "") return {};
  const n = Number(raw);
  return wholeIn(n, min, max) ? { value: n } : { error: message };
}

export function parseFilters(p: URLSearchParams): ParsedFilters {
  const errors: ParsedFilters["errors"] = {};
  const budgetMsg = `Use whole taka from ৳0 to ৳${MAX_BUDGET_TAKA.toLocaleString("en-US")}.`;
  const min = whole(p.get("budget_min"), 0, MAX_BUDGET_TAKA, budgetMsg);
  const max = whole(p.get("budget_max"), 0, MAX_BUDGET_TAKA, budgetMsg);
  const deadline = whole(
    p.get("deadline_max"),
    1,
    365,
    "Use a whole number of days from 1 to 365.",
  );
  const team = whole(p.get("team_size"), 2, 10, "Choose a team size from 2 to 10.");
  const hours = whole(p.get("hours"), 1, 168, "Use a whole number of hours from 1 to 168.");
  if (min.error) errors.budget_min = min.error;
  if (max.error) errors.budget_max = max.error;
  if (deadline.error) errors.deadline_max = deadline.error;
  if (team.error) errors.team_size = team.error;
  if (hours.error) errors.hours = hours.error;
  let budgetMax = max.value;
  if (min.value !== undefined && budgetMax !== undefined && budgetMax < min.value) {
    errors.budget_max = "Use a maximum at or above the minimum.";
    budgetMax = undefined;
  }
  const role = (p.get("role") ?? "").trim();
  const api: SearchFilters = {
    q: p.get("q") ?? "",
    skills: p.getAll("skills"),
    budget_min: min.value === undefined ? undefined : min.value * 100,
    budget_max: budgetMax === undefined ? undefined : budgetMax * 100,
    deadline_max: deadline.value,
    team_size: team.value,
    role: role === "" ? undefined : role.slice(0, 80),
    hours: hours.value,
    sort: p.get("sort") ?? "newest",
  };
  const active = FILTER_KEYS.some((k) => p.getAll(k).some((v) => v.trim() !== ""));
  return { api, errors, active };
}
