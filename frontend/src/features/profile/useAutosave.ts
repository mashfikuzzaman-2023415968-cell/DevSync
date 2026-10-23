/**
 * Autosave (spec §17 Phase 3): after the person stops typing for a moment, send only the
 * fields that changed; the indicator says "Saving…", "Saved" or what went wrong.
 *
 * Values are compared the way the server stores them (numbers as numbers, text without
 * surrounding spaces), otherwise "30" vs 30 or a trailing space would look like a change after
 * every save and autosave would never stop. An edit still waiting when the page is left is
 * saved on the way out, and closing the tab with one pending asks first.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type SaveState = "idle" | "saving" | "saved" | "error";
export const AUTOSAVE_DELAY_MS = 800;

/** Equal as the server would store them: trimmed text, numeric strings as numbers. */
export function sameValue(a: unknown, b: unknown): boolean {
  if (typeof a === "number" || typeof b === "number") {
    if (a === "" || b === "" || a == null || b == null) return a === b;
    return Number(a) === Number(b);
  }
  if (typeof a === "string" && typeof b === "string") return a.trim() === b.trim();
  return a === b;
}

export function changedFields<T extends Record<string, unknown>>(current: T, saved: T): Partial<T> {
  const out: Partial<T> = {};
  for (const key of Object.keys(current) as (keyof T)[]) {
    if (!sameValue(current[key], saved[key])) out[key] = current[key];
  }
  return out;
}

export function useAutosave<T extends Record<string, unknown>>(
  values: T,
  saved: T | undefined,
  save: (changes: Partial<T>) => Promise<void>,
  valid: boolean,
  /** Called for a field the person hasn't touched whose saved value changed elsewhere (another
   * tab, a refetch), so the form shows it instead of saving its old value back. */
  adopt?: (key: keyof T, value: T[keyof T]) => void,
  /** The form's live values (e.g. react-hook-form `getValues`): read when saving, since the
   * rendered `values` can trail the last keystroke by a render when the page is left. */
  read?: () => T,
) {
  const [state, setState] = useState<SaveState>("idle");
  const timer = useRef<number | undefined>(undefined);
  const latest = useRef(values);
  latest.current = values;
  const readRef = useRef(read);
  readRef.current = read;
  const current = useCallback(() => readRef.current?.() ?? latest.current, []);
  // The caller's save function may change identity on every render; keep the latest in a ref
  // so a failed save is retried only when the person edits again or presses "Try again".
  const saveRef = useRef(save);
  saveRef.current = save;
  const adoptRef = useRef(adopt);
  adoptRef.current = adopt;
  const savedRef = useRef(saved);
  const validRef = useRef(valid);
  validRef.current = valid;
  const failedKey = useRef<string | null>(null);

  const flush = useCallback(async () => {
    const base = savedRef.current;
    if (!base) return;
    const now = current();
    const changes = changedFields(now, base);
    if (Object.keys(changes).length === 0) return;
    setState("saving");
    try {
      await saveRef.current(changes);
      failedKey.current = null;
      setState("saved");
    } catch {
      failedKey.current = JSON.stringify(now);
      setState("error");
    }
  }, [current]);

  // A new saved version: adopt fields changed elsewhere that the person hasn't edited.
  useEffect(() => {
    const previous = savedRef.current;
    savedRef.current = saved;
    if (!previous || !saved || !adoptRef.current) return;
    for (const key of Object.keys(saved) as (keyof T)[]) {
      if (!sameValue(previous[key], saved[key]) && sameValue(current()[key], previous[key])) {
        adoptRef.current(key, saved[key]);
      }
    }
  }, [saved, current]);

  const key = JSON.stringify(values);
  useEffect(() => {
    if (!saved || !valid || failedKey.current === key) return undefined;
    if (Object.keys(changedFields(values, saved)).length === 0) return undefined;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = undefined;
      void flush();
    }, AUTOSAVE_DELAY_MS);
    return () => {
      window.clearTimeout(timer.current);
    };
    // `key` stands for the values (objects change identity on every render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, saved, valid, flush]);

  // Leaving the page (navigation inside the app): save what is still waiting. Closing the tab:
  // try to save and ask the browser to confirm.
  useEffect(() => {
    const pending = () =>
      validRef.current &&
      savedRef.current !== undefined &&
      Object.keys(changedFields(current(), savedRef.current)).length > 0;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!pending()) return;
      void flush();
      e.preventDefault();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.clearTimeout(timer.current);
      if (pending()) void flush();
    };
  }, [flush, current]);

  return { state, retry: flush };
}
