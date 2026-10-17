import { cn } from "@/lib/cn";

/** DevSync mark: three linked nodes, one amber (the newcomer). The same motif becomes the
 * 3D constellation on the homepage (spec §13.12–13.13). */
export function Mark({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <path
        d="M10 11 22 11 16 22Z"
        fill="none"
        className="stroke-on-primary"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="10" cy="11" r="3" className="fill-on-primary" />
      <circle cx="22" cy="11" r="3" className="fill-on-primary" />
      <circle cx="16" cy="22" r="3" className="fill-newcomer-bg" />
    </svg>
  );
}

export function Wordmark({
  className,
  compact = false,
}: {
  className?: string;
  compact?: boolean;
}) {
  return (
    <span
      className={cn(
        "flex items-center gap-2 text-h4 font-semibold tracking-tight text-text",
        className,
      )}
    >
      <Mark />
      <span className={cn(compact && "sr-only")}>DevSync</span>
    </span>
  );
}
