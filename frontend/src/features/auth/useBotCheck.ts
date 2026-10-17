/** Honeypot + minimum fill time + CAPTCHA for public forms (spec §14.16). */
import { useCallback, useRef, useState } from "react";
import { solveCaptcha } from "./api";

export function useBotCheck() {
  const startedAt = useRef(Date.now());
  const [solving, setSolving] = useState(false);
  const [honeypot, setHoneypot] = useState("");

  const fields = useCallback(
    async (withCaptcha: boolean) => {
      let captcha: string | null = null;
      if (withCaptcha) {
        setSolving(true);
        try {
          captcha = await solveCaptcha();
        } finally {
          setSolving(false);
        }
      }
      return { captcha, website: honeypot, started_at_ms: startedAt.current };
    },
    [honeypot],
  );

  return { fields, solving, honeypot, setHoneypot };
}
