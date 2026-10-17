/** Profile form validation mirroring backend/app/schemas/profiles.py (the server decides). */
import { z } from "zod";
import "@/features/auth/schemas"; // applies z.config({ jitless: true }) for the strict CSP

/** A full https:// address (checked with the URL parser, not a regular expression). */
export function isHttpsUrl(value: string): boolean {
  if (value === "") return true;
  if (/\s/.test(value)) return false;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname !== "";
  } catch {
    return false;
  }
}

/** GitHub usernames: 1–39 letters, digits or single hyphens, not starting or ending with one. */
export function isGithubUsername(value: string): boolean {
  return (
    value === "" ||
    (value.length <= 39 &&
      /^[A-Za-z0-9-]+$/.test(value) &&
      !value.startsWith("-") &&
      !value.endsWith("-") &&
      !value.includes("--"))
  );
}

const https = z
  .string()
  .trim()
  .max(300, "Use at most 300 characters.")
  .refine(isHttpsUrl, { message: "Use a full https:// address." });

export const aboutSchema = z.object({
  headline: z.string().trim().max(120, "Use at most 120 characters."),
  bio: z.string().trim().max(2000, "Use at most 2,000 characters."),
  hours_per_week: z.coerce
    .number({ error: "Enter a number of hours." })
    .int("Use whole hours.")
    .min(1, "At least 1 hour a week.")
    .max(80, "At most 80 hours a week."),
  github_username: z.string().trim().refine(isGithubUsername, {
    message: "Use your GitHub username (letters, digits and single hyphens).",
  }),
  timezone: z.string().min(1, "Choose a time zone."),
  visibility: z.enum(["PUBLIC", "CLIENTS_ONLY"]),
});
export type AboutValues = z.input<typeof aboutSchema>;

export const itemSchema = z.object({
  title: z.string().trim().min(1, "Give the item a title.").max(120, "Use at most 120 characters."),
  description: z.string().trim().max(2000, "Use at most 2,000 characters."),
  url: https,
  skill_ids: z.array(z.string()).max(8, "Pick at most 8 skills."),
});
export type ItemValues = z.infer<typeof itemSchema>;

export const certificateSchema = z.object({
  title: z.string().trim().min(1, "Enter the certificate’s name.").max(120),
  issuer: z.string().trim().min(1, "Enter who issued it.").max(120),
});
export type CertificateValues = z.infer<typeof certificateSchema>;

export const reviewSchema = z
  .object({
    source: z.string().trim().min(1, "Name the platform.").max(80, "Use at most 80 characters."),
    rating: z.coerce.number({ error: "Enter the rating." }).min(0, "Use 0 or more."),
    scale: z.coerce
      .number({ error: "Enter the top rating." })
      .int("Use a whole number.")
      .min(1, "Use at least 1.")
      .max(100, "Use at most 100."),
    project_date: z.iso.date("Choose the date the project ended."),
  })
  .refine((v) => v.rating <= v.scale, {
    path: ["rating"],
    message: "The rating can’t be above the top rating.",
  })
  .refine((v) => new Date(v.project_date) <= new Date(), {
    path: ["project_date"],
    message: "Use a date in the past.",
  });
export type ReviewValues = z.input<typeof reviewSchema>;

const MB = 1024 * 1024;
export const IMAGE_RULE = {
  types: ["image/png", "image/jpeg", "image/webp"],
  maxBytes: 20 * MB,
  description: "PNG, JPEG or WebP up to 20 MB",
} as const;
export const CERTIFICATE_RULE = {
  types: ["application/pdf", "image/png", "image/jpeg", "image/webp"],
  maxBytes: 10 * MB,
  description: "a PDF up to 10 MB, or an image",
} as const;
export const REVIEW_RULE = {
  types: ["application/pdf", "text/plain", "image/png", "image/jpeg", "image/webp"],
  maxBytes: 10 * MB,
  description: "a screenshot, PDF or text export up to 10 MB",
} as const;
