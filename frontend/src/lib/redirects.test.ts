import { describe, expect, it } from "vitest";
import { isSafePath, roleHome, safeRedirect } from "./redirects";

describe("redirect validator (mirrors backend/app/core/redirects.py)", () => {
  it.each([
    "/",
    "/client",
    "/client/projects/new",
    "/dev/bids/abc-123",
    "/admin",
    "/p/123",
    "/verify",
    "/w/p1/tasks",
    "/client?tab=x",
  ])("accepts %s", (path) => {
    expect(isSafePath(path)).toBe(true);
  });

  it.each([
    "//evil.com",
    "https://evil.com",
    "/\\evil.com",
    "javascript:alert(1)",
    "/%2F%2Fevil.com",
    "/%5Cevil.com",
    "/client\n/x",
    "/unknown",
    "/p",
    "/w",
    "/p/a/b",
    "",
    "client",
    "/" + "a".repeat(600),
    "/%E0%A4%A",
  ])("rejects %s", (path) => {
    expect(isSafePath(path)).toBe(false);
    expect(safeRedirect(path, "CLIENT")).toBe("/client");
  });

  it("sends pending users to verification and knows role homes", () => {
    expect(safeRedirect("/client", "CLIENT", "PENDING")).toBe("/verify");
    expect(roleHome("DEVELOPER")).toBe("/dev");
    expect(roleHome("ADMIN")).toBe("/admin");
    expect(roleHome(null)).toBe("/");
    expect(roleHome("CLIENT", "PENDING")).toBe("/verify");
  });

  it("never produces an off-site target for random input", () => {
    const alphabet = "/\\:.%a1?#@ \t";
    for (let i = 0; i < 2000; i += 1) {
      let s = "";
      for (let j = 0; j < 12; j += 1)
        s += alphabet.charAt(Math.floor(Math.random() * alphabet.length));
      const out = safeRedirect(s, "DEVELOPER");
      expect(out.startsWith("/")).toBe(true);
      expect(out.startsWith("//")).toBe(false);
      expect(out.includes("\\")).toBe(false);
    }
  });
});
