/** States and progress (spec §13.3, §13.8 #8): Alert, EmptyState, ErrorState (retry +
 * request id), Progress, Meter, RingProgress, Stepper, StatCard, PageHeader. */
import { motion } from "framer-motion";
import { Check, CircleAlert, CircleCheck, Info, RotateCw, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { meterTransition } from "@/design/motion";
import { useReducedMotion } from "@/design/preferences";
import { cn } from "@/lib/cn";
import { Button } from "./Button";
import { Card } from "./Display";
import { useCountUp } from "./useCountUp";

type AlertTone = "danger" | "success" | "info" | "warning";

const ALERT: Record<AlertTone, { box: string; icon: typeof Info; label: string }> = {
  danger: { box: "border-danger/25 bg-danger-bg text-danger", icon: CircleAlert, label: "Error" },
  success: {
    box: "border-success/25 bg-success-bg text-success",
    icon: CircleCheck,
    label: "Done",
  },
  info: { box: "border-info/25 bg-info-bg text-info", icon: Info, label: "Note" },
  warning: {
    box: "border-warning/25 bg-warning-bg text-warning",
    icon: TriangleAlert,
    label: "Warning",
  },
};

/** Inline status message with an icon and a text label, never colour alone (§13.6). */
export function Alert({
  tone,
  title,
  children,
  className,
}: {
  tone: AlertTone;
  title?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const t = ALERT[tone];
  const Icon = t.icon;
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn("flex gap-3 rounded-md border px-3.5 py-3 text-body-sm", t.box, className)}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0">
        <span className="sr-only">{t.label}: </span>
        {title ? <p className="font-semibold">{title}</p> : null}
        <div className={cn(title && "mt-0.5", "text-text")}>{children}</div>
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  art,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
  /** Optional still from the constellation family (spec §13.13). */
  art?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center px-6 py-12 text-center", className)}>
      {art ??
        (icon ? (
          <div className="flex size-12 items-center justify-center rounded-full bg-primary-soft text-primary [&_svg]:size-6">
            {icon}
          </div>
        ) : null)}
      <h2 className="mt-4 text-body font-semibold text-text">{title}</h2>
      <p className="mt-1 max-w-sm text-body-sm text-text-muted">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = "This didn’t load",
  description = "Check your connection and try again. If it keeps happening, share the request ID with support.",
  requestId,
  onRetry,
  className,
}: {
  title?: string;
  description?: string;
  requestId?: string | null;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn("flex flex-col items-center px-6 py-12 text-center", className)}
    >
      <div className="flex size-12 items-center justify-center rounded-full bg-danger-bg text-danger">
        <CircleAlert className="size-6" aria-hidden="true" />
      </div>
      <h2 className="mt-4 text-body font-semibold text-text">{title}</h2>
      <p className="mt-1 max-w-sm text-body-sm text-text-muted">{description}</p>
      {requestId ? (
        <p className="mt-2 text-caption text-text-muted">
          Request ID <span className="font-mono">{requestId}</span>
        </p>
      ) : null}
      {onRetry ? (
        <Button
          variant="outline"
          className="mt-5"
          onClick={onRetry}
          icon={<RotateCw aria-hidden="true" />}
        >
          Try again
        </Button>
      ) : null}
    </div>
  );
}

/** Linear progress / meter: width animates 400 ms emphasized (catalogue). */
export function Progress({
  value,
  max = 100,
  label,
  tone = "primary",
  showValue = false,
  className,
}: {
  value: number;
  max?: number;
  label: string;
  tone?: "primary" | "success" | "warning" | "danger" | "newcomer";
  showValue?: boolean;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className={className}>
      {showValue ? (
        <div className="mb-1.5 flex justify-between text-body-sm">
          <span className="text-text-muted">{label}</span>
          <span className="font-medium tabular text-text">{Math.round(pct)}%</span>
        </div>
      ) : null}
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        className="h-2 overflow-hidden rounded-full bg-surface-2"
      >
        <motion.div
          className={cn(
            "h-full rounded-full",
            tone === "primary" && "bg-primary",
            tone === "success" && "bg-success",
            tone === "warning" && "bg-warning",
            tone === "danger" && "bg-danger",
            tone === "newcomer" && "bg-newcomer",
          )}
          initial={{ width: reduced ? `${String(pct)}%` : "0%" }}
          animate={{ width: `${String(pct)}%` }}
          transition={meterTransition(reduced)}
        />
      </div>
    </div>
  );
}

/** Ring progress (dashboards, test scores). */
export function RingProgress({
  value,
  label,
  size = 64,
  children,
}: {
  value: number;
  label: string;
  size?: number;
  children?: ReactNode;
}) {
  const reduced = useReducedMotion();
  const r = 15.5;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
      className="relative inline-flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 36 36" className="size-full -rotate-90" aria-hidden="true">
        <circle cx="18" cy="18" r={r} fill="none" className="stroke-surface-2" strokeWidth="3" />
        <motion.circle
          cx="18"
          cy="18"
          r={r}
          fill="none"
          className="stroke-primary"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: reduced ? c * (1 - pct / 100) : c }}
          animate={{ strokeDashoffset: c * (1 - pct / 100) }}
          transition={meterTransition(reduced)}
        />
      </svg>
      <span className="absolute text-body-sm font-semibold tabular text-text">
        {children ?? `${String(Math.round(pct))}%`}
      </span>
    </div>
  );
}

export interface Step {
  label: string;
}

/** Stepper (wizards): full on desktop; "Step 3 of 6" + bar on phones (spec §13.14). */
export function Stepper({ steps, current }: { steps: Step[]; current: number }) {
  return (
    <nav aria-label="Progress">
      <div className="md:hidden">
        <p className="text-body-sm font-medium text-text">
          Step {current + 1} of {steps.length}
          <span className="text-text-muted"> · {steps[current]?.label}</span>
        </p>
        <Progress
          className="mt-2"
          value={current + 1}
          max={steps.length}
          label={`Step ${String(current + 1)} of ${String(steps.length)}`}
        />
      </div>
      <ol className="hidden items-center gap-2 md:flex">
        {steps.map((s, i) => {
          const done = i < current;
          const active = i === current;
          return (
            <li
              key={s.label}
              className="flex items-center gap-2"
              aria-current={active ? "step" : undefined}
            >
              <span
                className={cn(
                  "flex size-7 items-center justify-center rounded-full text-caption font-semibold tabular transition-colors duration-base",
                  done && "bg-primary text-on-primary",
                  active && "border-2 border-primary text-primary",
                  !done && !active && "border border-border text-text-muted",
                )}
              >
                {done ? <Check className="size-4" aria-hidden="true" /> : i + 1}
              </span>
              <span
                className={cn(
                  "text-body-sm",
                  active ? "font-semibold text-text" : "text-text-muted",
                )}
              >
                {s.label}
                {done ? <span className="sr-only"> (done)</span> : null}
              </span>
              {i < steps.length - 1 ? (
                <span className="mx-1 h-px w-6 bg-border" aria-hidden="true" />
              ) : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** Stat card: value (counts up on first view), label, optional delta and hint. */
export function StatCard({
  label,
  value,
  format = (v: number) => Math.round(v).toLocaleString("en-IN"),
  delta,
  hint,
  icon,
}: {
  label: string;
  value: number;
  format?: (value: number) => string;
  delta?: { value: string; direction: "up" | "down" | "flat"; good?: boolean };
  hint?: ReactNode;
  icon?: ReactNode;
}) {
  const [ref, shown] = useCountUp<HTMLParagraphElement>(value);
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-body-sm text-text-muted">{label}</p>
        {icon ? <span className="text-text-subtle [&_svg]:size-5">{icon}</span> : null}
      </div>
      <p ref={ref} className="mt-2 text-h2 font-semibold tabular tracking-tight text-text">
        <span aria-hidden="true">{format(shown)}</span>
        <span className="sr-only">{format(value)}</span>
      </p>
      {delta || hint ? (
        <p className="mt-1 flex items-center gap-2 text-caption text-text-muted">
          {delta ? (
            <span
              className={cn(
                "font-medium",
                delta.good === true && "text-success",
                delta.good === false && "text-danger",
              )}
            >
              {delta.direction === "up" ? "▲" : delta.direction === "down" ? "▼" : "•"}{" "}
              {delta.value}
            </span>
          ) : null}
          {hint}
        </p>
      ) : null}
    </Card>
  );
}

/** Page header (spec §13.8 #1): breadcrumb → h1 → one-line description → primary action.
 * On phones the action becomes a full-width button below (§13.14). */
export function PageHeader({
  title,
  description,
  action,
  breadcrumbs,
  children,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  breadcrumbs?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="mb-6">
      {breadcrumbs ? <div className="mb-3">{breadcrumbs}</div> : null}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-h3 font-semibold tracking-tight text-text">{title}</h1>
          {description ? <p className="mt-1 text-body text-text-muted">{description}</p> : null}
        </div>
        {action ? (
          <div className="w-full shrink-0 sm:w-auto [&>*]:w-full sm:[&>*]:w-auto">{action}</div>
        ) : null}
      </div>
      {children ? <div className="mt-4">{children}</div> : null}
    </header>
  );
}
