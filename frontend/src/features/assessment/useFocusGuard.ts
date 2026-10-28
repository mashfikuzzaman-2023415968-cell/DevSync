/**
 * Focus mode's leave detection (role assessment spec §7.3–§7.4). One "leave" is the page being
 * hidden (tab switch, minimise, app switch, reload, close), full screen being left while it was
 * on, or the window losing focus for longer than the debounce (short blurs from OS
 * notifications are ignored). Signals within 5 s of a counted leave are the same leave.
 *
 * Every counted leave gets the next `seq` and is sent to the server, which decides — warning
 * or the end of the attempt — and is idempotent by `seq`. While the page is being hidden the
 * request goes with `keepalive`; it is also written to sessionStorage and re-sent after a
 * reload or when the connection comes back, until the server acknowledges it.
 *
 * This runs in the browser and can be bypassed (§7.7); the server-side guarantees are the
 * deadline, one-way navigation, hidden answers and single-window tokens.
 */
import { useEffect, useRef } from "react";
import { ApiError } from "@/api/client";
import type { FocusEventResult, FocusEventType } from "@/api/types";
import { readSession, writeSession } from "@/lib/storage";
import { sendFocusEvent } from "./api";

export const COALESCE_MS = 5000;

export interface PendingLeave {
  seq: number;
  type: FocusEventType;
  client_at: string;
}

export function pendingKey(attemptId: string): string {
  return `devsync:pending-leaves:${attemptId}`;
}

/** Pure leave counting: decides whether a signal at `now` is a new leave (and its seq). */
export class LeaveCounter {
  private lastLeaveAt = -Infinity;
  private seq: number;

  constructor(
    startSeq: number,
    private readonly coalesceMs = COALESCE_MS,
  ) {
    this.seq = startSeq;
  }

  /** The new leave's seq, or null when this signal belongs to the previous leave. */
  signal(now: number): number | null {
    if (now - this.lastLeaveAt < this.coalesceMs) return null;
    this.lastLeaveAt = now;
    this.seq += 1;
    return this.seq;
  }

  get current(): number {
    return this.seq;
  }
}

export interface FocusGuardOptions {
  attemptId: string;
  enabled: boolean;
  /** Leaves the server already counted (its `focus_leaves`), so new ones continue from there. */
  serverLeaves: number;
  debounceMs: number;
  fullscreenSupported: boolean;
  onResult: (result: FocusEventResult) => void;
  onError?: (error: unknown) => void;
}

export function useFocusGuard({
  attemptId,
  enabled,
  serverLeaves,
  debounceMs,
  fullscreenSupported,
  onResult,
  onError,
}: FocusGuardOptions): void {
  const handlers = useRef({ onResult, onError });
  handlers.current = { onResult, onError };

  useEffect(() => {
    if (!enabled) return undefined;
    const key = pendingKey(attemptId);
    const pending = readSession<PendingLeave[]>(key, []);
    const counter = new LeaveCounter(Math.max(serverLeaves, ...pending.map((p) => p.seq)));
    let fullscreenWasOn = document.fullscreenElement !== null;
    let blurTimer: number | undefined;
    let firstEvent = true;
    let disposed = false;

    const store = (list: PendingLeave[]) => {
      writeSession(key, list.length ? list : null);
    };
    const send = async (leave: PendingLeave, keepalive: boolean) => {
      try {
        const body = {
          ...leave,
          ...(firstEvent ? { fullscreen_supported: fullscreenSupported } : {}),
        };
        firstEvent = false;
        const result = await sendFocusEvent(attemptId, body, keepalive);
        store(readSession<PendingLeave[]>(key, []).filter((p) => p.seq !== leave.seq));
        if (!disposed) handlers.current.onResult(result);
      } catch (error) {
        // A refusal the server made on purpose (moved window, closed attempt) is final; a
        // network failure keeps the leave pending for the next try.
        if (error instanceof ApiError && error.status !== 0 && error.status < 500) {
          store(readSession<PendingLeave[]>(key, []).filter((p) => p.seq !== leave.seq));
        }
        if (!disposed) handlers.current.onError?.(error);
      }
    };
    const leave = (type: FocusEventType, keepalive = false) => {
      const seq = counter.signal(Date.now());
      if (seq === null) return;
      const entry: PendingLeave = { seq, type, client_at: new Date().toISOString() };
      store([...readSession<PendingLeave[]>(key, []), entry]);
      void send(entry, keepalive);
    };
    const resendPending = () => {
      for (const p of readSession<PendingLeave[]>(key, [])) void send(p, false);
    };

    const onVisibility = () => {
      if (document.visibilityState === "hidden") leave("VISIBILITY_HIDDEN", true);
    };
    const onPageHide = () => {
      leave("PAGE_UNLOAD", true);
    };
    const onFullscreen = () => {
      if (document.fullscreenElement === null && fullscreenWasOn) leave("FULLSCREEN_EXIT");
      fullscreenWasOn = document.fullscreenElement !== null;
    };
    const onBlur = () => {
      window.clearTimeout(blurTimer);
      blurTimer = window.setTimeout(() => {
        if (!document.hasFocus()) leave("WINDOW_BLUR");
      }, debounceMs);
    };
    const onFocus = () => {
      window.clearTimeout(blurTimer);
    };

    resendPending(); // leaves a reload interrupted (the server ignores ones it already has)
    document.addEventListener("visibilitychange", onVisibility);
    document.addEventListener("fullscreenchange", onFullscreen);
    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    window.addEventListener("online", resendPending);
    return () => {
      disposed = true;
      window.clearTimeout(blurTimer);
      document.removeEventListener("visibilitychange", onVisibility);
      document.removeEventListener("fullscreenchange", onFullscreen);
      window.removeEventListener("pagehide", onPageHide);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("online", resendPending);
    };
    // serverLeaves is read once when guarding starts; later changes come from our own leaves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attemptId, enabled, debounceMs, fullscreenSupported]);
}
