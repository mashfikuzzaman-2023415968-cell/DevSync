/**
 * In-house ALTCHA v1 solver (spec §14.16, DECISIONS D19): find n with
 * SHA-256(salt + n) = challenge using the browser's Web Crypto, then send back
 * base64(JSON{algorithm, challenge, number, salt, signature}). No third-party
 * widget, no injected styles or blob workers, so it works under the strict CSP.
 */
export interface CaptchaChallenge {
  algorithm: "SHA-256";
  challenge: string;
  max_number: number;
  salt: string;
  signature: string;
}

const encoder = new TextEncoder();

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function solveChallenge(
  c: CaptchaChallenge,
  signal?: AbortSignal,
): Promise<string | null> {
  for (let n = 0; n <= c.max_number; n += 1) {
    if (signal?.aborted) return null;
    if ((await sha256Hex(`${c.salt}${String(n)}`)) === c.challenge) {
      const payload = {
        algorithm: c.algorithm,
        challenge: c.challenge,
        number: n,
        salt: c.salt,
        signature: c.signature,
      };
      return btoa(JSON.stringify(payload));
    }
  }
  return null;
}
