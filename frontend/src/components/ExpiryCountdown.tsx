/**
 * Invitation countdown (spec §13.5 #9/#25; Phase 8). The server's `expires_at` is the truth:
 * the text is "2 days 4 h left", turning amber under 6 hours, and updates once a minute (also
 * under reduced motion, so nothing ticks every second). Screen readers get a static "Expires
 * 14 Dec, 15:30" (Asia/Dhaka) instead of an announcement every minute.
 */
import { Clock } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";

const MINUTE = 60_000;
const WARN_MS = 6 * 60 * MINUTE;

export function timeLeft(expiresAt: string, now: number): string {
  const ms = new Date(expiresAt).getTime() - now;
  if (ms <= 0) return "Expired";
  const minutes = Math.floor(ms / MINUTE);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days > 0) return `${String(days)} ${days === 1 ? "day" : "days"} ${String(hours)} h left`;
  if (hours > 0) return `${String(hours)} h ${String(mins)} min left`;
  return `${String(Math.max(mins, 1))} min left`;
}

export function ExpiryCountdown({
  expiresAt,
  className,
}: {
  expiresAt: string;
  className?: string;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => {
      setNow(Date.now());
    }, MINUTE);
    return () => {
      window.clearInterval(t);
    };
  }, []);
  const soon = new Date(expiresAt).getTime() - now < WARN_MS;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-body-sm tabular",
        soon ? "font-medium text-warning" : "text-text-muted",
        className,
      )}
      data-volatile
    >
      <Clock className="size-4" aria-hidden="true" />
      <span aria-hidden="true">{timeLeft(expiresAt, now)}</span>
      <span className="sr-only">Expires {formatDateTime(expiresAt)}</span>
    </span>
  );
}
