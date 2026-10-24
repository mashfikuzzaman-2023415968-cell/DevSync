import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { ApiError } from "@/api/client";

/** One sentence that says what happened and what to do next (spec §13.10). */
export function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429 && error.retryAfter) {
      return `Too many attempts. Try again in ${String(error.retryAfter)} seconds.`;
    }
    if (error.code === "CSRF_FAILED") return "Your form expired. Refresh the page and try again.";
    return error.message;
  }
  return "Something went wrong. Please try again.";
}

/** Show server-side field errors next to the matching inputs; returns true if any matched. */
export function applyFieldErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  known: readonly Path<T>[],
  /** Server field name → form field, where they differ (e.g. the server's password rules say
   * "password" for a form's "new_password"). */
  aliases: Partial<Record<string, Path<T>>> = {},
): boolean {
  if (!(error instanceof ApiError)) return false;
  let matched = false;
  for (const [serverField, message] of Object.entries(error.fields)) {
    const field = aliases[serverField] ?? serverField;
    const name = known.find((k) => k === field);
    if (name) {
      setError(name, { type: "server", message });
      matched = true;
    }
  }
  return matched;
}
