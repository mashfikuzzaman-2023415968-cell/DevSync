/** Honeypot + minimum fill time + CAPTCHA for public forms (spec §14.16). */
import { useCallback, useRef, useState } from "react";
import { solveCaptcha } from "./api";

/**
 * The server rejects forms sent less than 2 s after they were opened. A person
 * using a password manager can be that fast, so the form waits out the rest
 * instead of failing. Unit tests set this to 0.
 */
export const botTiming = { minFillMs: 2000 };

function waitFor(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function useBotCheck() {
  const startedAt = useRef(Date.now());
  const [solving, setSolving] = useState(false);
  const [honeypot, setHoneypot] = useState("");

  const fields = useCallback(
    async (withCaptcha: boolean) => {
      let captcha: string | null = null;
      setSolving(true);
      try {
        if (withCaptcha) captcha = await solveCaptcha();
        // A small margin covers clock rounding between browser and server.
        const remaining = botTiming.minFillMs + 100 - (Date.now() - startedAt.current);
        if (botTiming.minFillMs > 0 && remaining > 0) await waitFor(remaining);
      } finally {
        setSolving(false);
      }
      return { captcha, website: honeypot, started_at_ms: startedAt.current };
    },
    [honeypot],
  );

  return { fields, solving, honeypot, setHoneypot };
}
