import { cn } from "@/lib/cn";

/** Small loading indicator; static under reduced motion (the label still says "Loading"). */
export function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <span
      role={label ? "status" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn(
        "inline-block size-4 shrink-0 animate-[ds-spin_0.7s_linear_infinite] rounded-full border-2 border-current border-r-transparent",
        className,
      )}
    />
  );
}
