/** Form schemas for the workspace, mirroring the backend contracts (spec §13.7; D143, D148). */
import { z } from "zod";

const ESTIMATE = /^\d{1,3}(\.\d)?$/;

export const taskFormSchema = z.object({
  milestone_id: z.string().min(1, "Choose a milestone"),
  title: z.string().trim().min(1, "Give the task a title").max(160, "Keep it under 160 characters"),
  description: z.string().max(5000, "Keep it under 5,000 characters"),
  assignee_id: z.string(),
  deadline: z.string().refine((v) => v === "" || /^\d{4}-\d{2}-\d{2}$/.test(v), "Use a date"),
  estimate_hours: z
    .string()
    .trim()
    .regex(ESTIMATE, "Hours with at most one decimal, like 8 or 2.5")
    .refine((v) => Number(v) > 0, "More than 0 hours")
    .refine((v) => Number(v) <= 999.9, "At most 999.9 hours"),
  difficulty: z.enum(["EASY", "MEDIUM", "HARD"]),
});
export type TaskForm = z.infer<typeof taskFormSchema>;

const PR = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/pull\/[0-9]+$/;

/** A link (LINK, PR) or one of the project's files (FILE, SCREENSHOT = an image file). */
export const evidenceFormSchema = z
  .object({
    kind: z.enum(["LINK", "PR", "FILE", "SCREENSHOT"]),
    url: z.string().trim().max(2048, "Links are at most 2,048 characters"),
    file_id: z.string(),
    note: z.string().trim().max(500, "Keep the note under 500 characters"),
  })
  .refine((v) => !isLink(v.kind) || v.url.startsWith("https://"), {
    path: ["url"],
    message: "Links start with https://",
  })
  .refine((v) => v.kind !== "PR" || PR.test(v.url), {
    path: ["url"],
    message: "A pull request link looks like https://github.com/owner/repo/pull/12",
  })
  .refine((v) => isLink(v.kind) || v.file_id !== "", {
    path: ["file_id"],
    message: "Choose a file from the project’s Files",
  });

function isLink(kind: string): boolean {
  return kind === "LINK" || kind === "PR";
}
export type EvidenceForm = z.infer<typeof evidenceFormSchema>;
