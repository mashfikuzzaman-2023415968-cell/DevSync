/** Create-project form validation, mirroring backend/app/schemas/projects.py (server decides). */
import { z } from "zod";
import "@/features/auth/schemas"; // applies z.config({ jitless: true }) for the strict CSP

export const infoSchema = z.object({
  title: z
    .string()
    .trim()
    .min(5, "Give the project a title of at least 5 characters.")
    .max(120, "Use at most 120 characters."),
  summary: z.string().trim().max(300, "Use at most 300 characters."),
});
export type InfoValues = z.infer<typeof infoSchema>;

export const requirementsSchema = z.object({
  description: z.string().trim().max(10_000, "Use at most 10,000 characters."),
  requirements: z.string().trim().max(5_000, "Use at most 5,000 characters."),
  deadline_days: z.coerce
    .number({ error: "Enter the number of days." })
    .int("Use whole days.")
    .min(1, "The deadline must be at least 1 day.")
    .max(365, "Use at most 365 days."),
  start_date: z.string().trim(),
});
export type RequirementsValues = z.infer<typeof requirementsSchema>;

export const teamSchema = z.object({
  team_size: z.coerce
    .number({ error: "Enter a team size." })
    .int("Use a whole number.")
    .min(2, "A team needs at least 2 people.")
    .max(10, "Use at most 10 people."),
});

/** One slot row in the Skills & team step. */
export interface SlotRow {
  skill_id: string;
  count: number;
  label: string;
}

/** One milestone row in the Milestones step; `key` is a stable local id for dependencies. */
export interface MilestoneRow {
  key: string;
  name: string;
  duration_days: number;
  share_bp: number;
  skill_ids: string[];
  predecessor_keys: string[];
  /** Server id once the milestone has been saved (lets re-saves update in place). */
  savedId?: string | undefined;
}

export const budgetSchema = z.object({
  budget_taka: z.coerce
    .number({ error: "Enter a budget." })
    .min(1, "Set a budget before you publish.")
    .max(100_000_000, "That budget looks too large."),
  bonus_taka: z.coerce
    .number({ error: "Enter a bonus, or 0." })
    .min(0, "A bonus cannot be negative.")
    .max(100_000_000, "That bonus looks too large."),
  bidding_deadline: z.string().trim(),
});
export type BudgetValues = z.infer<typeof budgetSchema>;

/** Taka (what the client types) to integer paisa (how money is stored). */
export const toPaisa = (taka: number): number => Math.round(taka * 100);
export const toTaka = (paisa: number): number => paisa / 100;

export const SHARE_TOTAL_BP = 10_000;

let counter = 0;
export function newKey(): string {
  counter += 1;
  return `m${String(counter)}-${Math.random().toString(36).slice(2, 7)}`;
}
