/** Display components (spec §13.3, §13.8): Card, Badge (icon + text, never colour alone),
 * NewcomerBadge, RiskChip, Avatar (initials; newcomer ring), Skeleton, Breadcrumbs. */
import * as AvatarPrimitive from "@radix-ui/react-avatar";
import {
  ChevronRight,
  CircleAlert,
  CircleCheck,
  CircleDot,
  Info,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";
import { Link } from "react-router";
import { cn } from "@/lib/cn";

export function Card({
  className,
  interactive = false,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  return (
    <div
      {...rest}
      className={cn(
        "rounded-lg border border-border bg-surface shadow-xs",
        interactive &&
          "transition-[box-shadow,border-color,transform] duration-base ease-standard hover:border-primary/30 hover:shadow-md motion-ok:hover:-translate-y-0.5",
        className,
      )}
    />
  );
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start justify-between gap-4 px-5 pt-5", className)}>
      <div className="min-w-0">
        <h2 className="text-body font-semibold text-text">{title}</h2>
        {description ? <p className="mt-0.5 text-body-sm text-text-muted">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export type Tone = "neutral" | "primary" | "success" | "warning" | "danger" | "info" | "newcomer";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-surface-2 text-text-muted",
  primary: "bg-primary-soft text-primary",
  success: "bg-success-bg text-success",
  warning: "bg-warning-bg text-warning",
  danger: "bg-danger-bg text-danger",
  info: "bg-info-bg text-info",
  newcomer: "bg-newcomer-bg text-newcomer",
};

const TONE_ICON: Record<Tone, typeof Info> = {
  neutral: CircleDot,
  primary: CircleDot,
  success: CircleCheck,
  warning: TriangleAlert,
  danger: CircleAlert,
  info: Info,
  newcomer: Sparkles,
};

export function Badge({
  tone = "neutral",
  children,
  icon = true,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  icon?: boolean;
  className?: string | undefined;
}) {
  const Icon = TONE_ICON[tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-caption font-medium",
        TONE_CLASS[tone],
        className,
      )}
    >
      {icon ? <Icon className="size-3.5" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

export function NewcomerBadge({ className }: { className?: string }) {
  return (
    <Badge tone="newcomer" className={className}>
      Newcomer
    </Badge>
  );
}

export type Severity = "CRITICAL" | "MEDIUM" | "LOW";

const SEVERITY: Record<Severity, { tone: Tone; label: string }> = {
  CRITICAL: { tone: "danger", label: "Critical" },
  MEDIUM: { tone: "warning", label: "Medium" },
  LOW: { tone: "info", label: "Low" },
};

/** Risk chip: severity icon + text (spec §13.3); CRITICAL pulses twice on first appearance. */
export function RiskChip({ severity, children }: { severity: Severity; children?: ReactNode }) {
  const s = SEVERITY[severity];
  return (
    <Badge
      tone={s.tone}
      className={cn(severity === "CRITICAL" && "motion-ok:animate-[ds-pop_0.6s_ease-out_2]")}
    >
      {s.label}
      {children ? <span className="font-normal">· {children}</span> : null}
    </Badge>
  );
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : [parts[0] ?? "?"];
  return letters
    .map((p) => (p ?? "").charAt(0))
    .join("")
    .toUpperCase();
}

export function Avatar({
  name,
  src,
  size = "md",
  newcomer = false,
}: {
  name: string;
  src?: string;
  size?: "sm" | "md" | "lg";
  newcomer?: boolean;
}) {
  return (
    <AvatarPrimitive.Root
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary-soft font-semibold text-primary",
        size === "sm" && "size-8 text-caption",
        size === "md" && "size-10 text-body-sm",
        size === "lg" && "size-14 text-body",
        newcomer && "ring-2 ring-newcomer ring-offset-2 ring-offset-surface",
      )}
    >
      {src ? <AvatarPrimitive.Image src={src} alt="" className="size-full object-cover" /> : null}
      <AvatarPrimitive.Fallback aria-hidden="true">{initials(name)}</AvatarPrimitive.Fallback>
      <span className="sr-only">{name}</span>
    </AvatarPrimitive.Root>
  );
}

/** Skeleton block matching the final layout; shimmer stops under reduced motion. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("skeleton rounded-md", className)} />;
}

export interface Crumb {
  label: string;
  to?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-1 text-body-sm text-text-muted">
        {items.map((c, i) => {
          const last = i === items.length - 1;
          return (
            <li key={`${c.label}-${String(i)}`} className="flex items-center gap-1">
              {c.to && !last ? (
                <Link to={c.to} className="rounded-sm hover:text-text hover:underline">
                  {c.label}
                </Link>
              ) : (
                <span aria-current={last ? "page" : undefined} className={cn(last && "text-text")}>
                  {c.label}
                </span>
              )}
              {!last ? <ChevronRight className="size-3.5" aria-hidden="true" /> : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
