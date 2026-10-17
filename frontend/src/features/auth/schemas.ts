/** Form validation mirroring backend/app/schemas/auth.py (server stays the authority). */
import { z } from "zod";

export const email = z.email("Enter a valid email address.").max(254);
export const password = z
  .string()
  .min(10, "Use at least 10 characters.")
  .max(128, "Use at most 128 characters.");
export const phone = z
  .string()
  .transform((v) => v.replace(/[\s-]/g, ""))
  .pipe(z.string().regex(/^\+[1-9]\d{7,14}$/, "Use international format, e.g. +8801712345678."));
export const displayName = z
  .string()
  .trim()
  .min(1, "Enter your name.")
  .max(80, "Use at most 80 characters.");
export const sixDigits = z.string().regex(/^\d{6}$/, "Enter the 6-digit code.");

export const loginSchema = z.object({ email, password: z.string().min(1, "Enter your password.") });
export type LoginValues = z.infer<typeof loginSchema>;

export const registerSchema = z.object({
  display_name: displayName,
  email,
  phone,
  password,
  accept_terms: z.literal(true, { error: "Accept the terms to continue." }),
});
export type RegisterValues = z.input<typeof registerSchema>;

export const forgotSchema = z.object({ email });
export const resetSchema = z
  .object({ new_password: password, confirm: z.string() })
  .refine((v) => v.new_password === v.confirm, {
    path: ["confirm"],
    message: "The passwords don’t match.",
  });
export const changePasswordSchema = z.object({
  current_password: z.string().min(1, "Enter your current password."),
  new_password: password,
});
