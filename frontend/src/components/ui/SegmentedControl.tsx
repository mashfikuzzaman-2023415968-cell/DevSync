/** Segmented control with a sliding indicator (catalogue: tabs/segmented 180 ms). A radio
 * group for assistive technology; arrow keys move the choice. */
import { motion } from "framer-motion";
import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { indicatorTransition } from "@/design/motion";
import { useReducedMotion } from "@/design/preferences";
import { cn } from "@/lib/cn";

export interface Segment<T extends string> {
  value: T;
  label: ReactNode;
}

interface Props<T extends string> {
  label: string;
  value: T;
  onChange: (value: T) => void;
  segments: readonly Segment<T>[];
  className?: string;
  size?: "sm" | "md";
}

export function SegmentedControl<T extends string>({
  label,
  value,
  onChange,
  segments,
  className,
  size = "md",
}: Props<T>) {
  const reduced = useReducedMotion();
  const layoutId = useId();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const index = Math.max(
    0,
    segments.findIndex((s) => s.value === value),
  );

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    const delta =
      e.key === "ArrowRight" || e.key === "ArrowDown"
        ? 1
        : e.key === "ArrowLeft" || e.key === "ArrowUp"
          ? -1
          : 0;
    if (!delta) return;
    e.preventDefault();
    const next = (index + delta + segments.length) % segments.length;
    const seg = segments[next];
    if (seg) {
      onChange(seg.value);
      refs.current[next]?.focus();
    }
  };

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn("inline-flex rounded-lg bg-surface-2 p-1", className)}
    >
      {segments.map((s, i) => {
        const active = s.value === value;
        return (
          <button
            key={s.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            onKeyDown={onKeyDown}
            onClick={() => {
              onChange(s.value);
            }}
            className={cn(
              "relative min-h-11 flex-1 rounded-md px-4 font-medium transition-colors duration-fast focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
              size === "sm" ? "min-h-9 px-3 text-body-sm" : "text-body-sm",
              active ? "text-text" : "text-text-muted hover:text-text",
            )}
          >
            {active ? (
              <motion.span
                layoutId={layoutId}
                transition={indicatorTransition(reduced)}
                className="absolute inset-0 rounded-md bg-surface shadow-sm"
                aria-hidden="true"
              />
            ) : null}
            <span className="relative">{s.label}</span>
          </button>
        );
      })}
    </div>
  );
}
