import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { solveChallenge } from "./captcha";

function challengeFor(salt: string, n: number) {
  return {
    algorithm: "SHA-256" as const,
    challenge: createHash("sha256")
      .update(`${salt}${String(n)}`)
      .digest("hex"),
    max_number: 50,
    salt,
    signature: "sig",
  };
}

describe("ALTCHA solver", () => {
  it("finds the number and encodes the payload", async () => {
    const payload = await solveChallenge(challengeFor("abc?expires=1", 37));
    expect(payload).not.toBeNull();
    const decoded = JSON.parse(atob(payload ?? "")) as Record<string, unknown>;
    expect(decoded).toEqual({
      algorithm: "SHA-256",
      challenge: challengeFor("abc?expires=1", 37).challenge,
      number: 37,
      salt: "abc?expires=1",
      signature: "sig",
    });
  });

  it("returns null when unsolvable or aborted", async () => {
    const c = { ...challengeFor("x", 99), max_number: 10 };
    expect(await solveChallenge(c)).toBeNull();
    const controller = new AbortController();
    controller.abort();
    expect(await solveChallenge(challengeFor("y", 5), controller.signal)).toBeNull();
  });
});
