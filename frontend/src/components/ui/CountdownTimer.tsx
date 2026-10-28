/**
 * Countdown for timed tests (spec §13.5 #14): the server's deadline is the truth; the client
 * only corrects for its own clock offset (from `server_now`). Amber under a minute, danger
 * under 15 seconds, always with an icon and words as well as colour; screen readers hear the
 * two warnings once, not every second.
 */
import { AlarmClock, Clock } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";

const TICK_MS = 1000;
export const WARN_SECONDS = 60;
export const DANGER_SECONDS = 15;

export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.ceil(totalSeconds));
  const minutes = Math.floor(s / 60);
  const seconds = s % 60;
  return `${String(minutes)}:${String(seconds).padStart(2, "0")}`;
}

/** Seconds left, given the deadline and the offset between server and client clocks. */
export function secondsLeft(deadline: Date, offsetMs: number, now = Date.now()): number {
  return Math.max(0, (deadline.getTime() - (now + offsetMs)) / 1000);
}

function minutesWords(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  return minutes === 1 ? "1 minute" : `${String(minutes)} minutes`;
}

export function CountdownTimer({
  deadline,
  offsetMs = 0,
  onExpire,
  className,
  warnAt = WARN_SECONDS,
  dangerAt = DANGER_SECONDS,
  announceAt,
}: {
  deadline: Date;
  /** server time − client time, in ms. */
  offsetMs?: number;
  onExpire?: () => void;
  className?: string;
  /** Amber from this many seconds left (default 60). */
  warnAt?: number;
  /** Rose from this many seconds left (default 15). */
  dangerAt?: number;
  /** Seconds-left marks announced to screen readers once each (e.g. 300, 120, 60); by default
   * only the two colour changes are announced. */
  announceAt?: readonly number[];
}) {
  const [left, setLeft] = useState(() => secondsLeft(deadline, offsetMs));
  const expired = useRef(false);
  useEffect(() => {
    expired.current = false;
    const tick = () => {
      const value = secondsLeft(deadline, offsetMs);
      setLeft(value);
      if (value <= 0 && !expired.current) {
        expired.current = true;
        onExpire?.();
      }
    };
    tick();
    const id = window.setInterval(tick, TICK_MS);
    return () => {
      window.clearInterval(id);
    };
  }, [deadline, offsetMs, onExpire]);

  const level = left <= dangerAt ? "danger" : left <= warnAt ? "warning" : "normal";
  let announcement: string;
  if (announceAt) {
    const mark = [...announceAt].sort((a, b) => a - b).find((m) => left <= m);
    announcement = mark !== undefined ? `${minutesWords(mark)} left.` : "";
  } else {
    announcement =
      level === "danger"
        ? "Less than 15 seconds left."
        : level === "warning"
          ? "Less than a minute left."
          : "";
  }
  const Icon = level === "normal" ? Clock : AlarmClock;
  return (
    <div
      data-level={level}
      className={cn(
        "inline-flex min-h-11 items-center gap-2 rounded-full border px-3.5 text-body font-semibold tabular",
        level === "normal" && "border-border bg-surface text-text",
        level === "warning" && "border-warning bg-warning-bg text-warning",
        level === "danger" && "border-danger bg-danger-bg text-danger",
        className,
      )}
    >
      <Icon className="size-4" aria-hidden="true" />
      <span role="timer" aria-label={`Time left ${formatClock(left)}`}>
        {formatClock(left)}
      </span>
      {level !== "normal" ? (
        <span className="text-body-sm font-medium">
          {level === "danger" ? "Hurry" : warnAt > WARN_SECONDS ? "Almost done" : "Under a minute"}
        </span>
      ) : null}
      <span className="sr-only" aria-live="polite">
        {announcement}
      </span>
    </div>
  );
}
