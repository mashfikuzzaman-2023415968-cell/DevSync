/**
 * Autosave (spec §17 Phase 3): after the person stops typing for a moment, send only the
 * fields that changed; the indicator says "Saving…", "Saved" or what went wrong.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type SaveState = "idle" | "saving" | "saved" | "error";
export const AUTOSAVE_DELAY_MS = 800;

export function changedFields<T extends Record<string, unknown>>(current: T, saved: T): Partial<T> {
  const out: Partial<T> = {};
  for (const key of Object.keys(current) as (keyof T)[]) {
    if (current[key] !== saved[key]) out[key] = current[key];
  }
  return out;
}

export function useAutosave<T extends Record<string, unknown>>(
  values: T,
  saved: T | undefined,
  save: (changes: Partial<T>) => Promise<void>,
  valid: boolean,
) {
  const [state, setState] = useState<SaveState>("idle");
  const timer = useRef<number | undefined>(undefined);
  const latest = useRef(values);
  latest.current = values;

  const flush = useCallback(async () => {
    if (!saved) return;
    const changes = changedFields(latest.current, saved);
    if (Object.keys(changes).length === 0) return;
    setState("saving");
    try {
      await save(changes);
      setState("saved");
    } catch {
      setState("error");
    }
  }, [save, saved]);

  const key = JSON.stringify(values);
  useEffect(() => {
    if (!saved || !valid) return undefined;
    if (Object.keys(changedFields(values, saved)).length === 0) return undefined;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      void flush();
    }, AUTOSAVE_DELAY_MS);
    return () => {
      window.clearTimeout(timer.current);
    };
    // `key` stands for the values (objects change identity on every render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, saved, valid, flush]);

  return { state, retry: flush };
}
