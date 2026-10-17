import { describe, expect, it } from "vitest";
import { changePasswordSchema, loginSchema, registerSchema, resetSchema } from "./schemas";

const valid = {
  display_name: "Nadia Rahman",
  email: "nadia@example.com",
  phone: "+880 1712-345678",
  password: "correct horse 42!",
  accept_terms: true as const,
};

describe("auth form schemas mirror the backend limits", () => {
  it("accepts a valid registration and normalizes the phone", () => {
    const parsed = registerSchema.parse(valid);
    expect(parsed.phone).toBe("+8801712345678");
  });

  it.each([
    ["display_name", ""],
    ["display_name", "x".repeat(81)],
    ["email", "not-an-email"],
    ["phone", "01712345678"],
    ["password", "short"],
    ["password", "x".repeat(129)],
    ["accept_terms", false],
  ])("rejects %s=%s", (field, value) => {
    const result = registerSchema.safeParse({ ...valid, [field]: value });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.path[0]).toBe(field);
  });

  it("login, reset and change-password rules", () => {
    expect(loginSchema.safeParse({ email: "a@b.co", password: "" }).success).toBe(false);
    expect(
      resetSchema.safeParse({ new_password: "correct horse 42!", confirm: "different" }).success,
    ).toBe(false);
    expect(
      resetSchema.safeParse({ new_password: "correct horse 42!", confirm: "correct horse 42!" })
        .success,
    ).toBe(true);
    expect(
      changePasswordSchema.safeParse({ current_password: "", new_password: "correct horse 42!" })
        .success,
    ).toBe(false);
  });
});
