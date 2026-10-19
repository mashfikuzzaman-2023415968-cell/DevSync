/**
 * Compact multi-select as toggle chips (the app has no MultiSelect yet; spec §13.3 lists it as
 * to-build). Each option is a button with `aria-pressed`; the whole group is a listbox-like set
 * of toggles, keyboard-reachable and labelled by the field it sits in.
 */
import { Check } from "lucide-react";
import { cn } from "@/lib/cn";

export interface TagOption {
  value: string;
  label: string;
}

export function TagPicker({
  options,
  value,
  onChange,
  id,
  "aria-describedby": describedBy,
  empty = "No options yet.",
}: {
  options: TagOption[];
  value: string[];
  onChange: (next: string[]) => void;
  id?: string | undefined;
  "aria-describedby"?: string | undefined;
  empty?: string;
}) {
  if (options.length === 0) {
    return <p className="text-caption text-text-muted">{empty}</p>;
  }
  const toggle = (v: string) => {
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  };
  return (
    <div id={id} aria-describedby={describedBy} className="flex flex-wrap gap-2">
      {options.map((o) => {
        const on = value.includes(o.value);
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            onClick={() => {
              toggle(o.value);
            }}
            className={cn(
              "inline-flex min-h-8 items-center gap-1 rounded-full border px-3 py-1 text-body-sm transition-colors duration-fast focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
              on
                ? "border-primary bg-primary-soft text-primary"
                : "border-border text-text-muted hover:border-text-subtle",
            )}
          >
            {on ? <Check className="size-3.5" aria-hidden="true" /> : null}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
