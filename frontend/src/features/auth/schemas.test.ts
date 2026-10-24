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
    ["phone", "+88012345"],
    ["phone", "+8802123456789"],
    ["phone", "12345"],
    ["password", "   short    "],
    ["password", "short"],
    ["password", "x".repeat(129)],
    ["accept_terms", false],
  ])("rejects %s=%s", (field, value) => {
    const result = registerSchema.safeParse({ ...valid, [field]: value });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.path[0]).toBe(field);
  });

  it.each([
    ["+88001712345678", "+8801712345678"], // the "+880" prefill, then the local number
    ["01712345678", "+8801712345678"],
    ["+880 1712-345678", "+8801712345678"],
    ["+447911123456", "+447911123456"],
  ])("reads the phone %s as %s, like the server", (written, stored) => {
    expect(registerSchema.parse({ ...valid, phone: written }).phone).toBe(stored);
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

describe("zod runs without eval (strict CSP, spec §14.3)", () => {
  it("is configured jitless once the schemas load", async () => {
    const { z } = await import("zod");
    await import("./schemas");
    expect(z.config().jitless).toBe(true);
  });
});
