import { Check, Circle } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { cn } from "@/lib/cn";

export interface ChecklistItem {
  label: string;
  done: boolean;
  hint: ReactNode;
  to?: string;
}

/** Onboarding checklist (spec §13.5 #9): done items are ticked; open items say what to do. */
export function Checklist({ items }: { items: ChecklistItem[] }) {
  return (
    <ol className="divide-y divide-border">
      {items.map((item) => (
        <li key={item.label} className="flex items-start gap-3 px-5 py-4">
          <span
            className={cn(
              "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full",
              item.done ? "bg-success-bg text-success" : "border border-border text-text-subtle",
            )}
          >
            {item.done ? (
              <Check className="size-4" aria-hidden="true" />
            ) : (
              <Circle className="size-2.5" aria-hidden="true" />
            )}
          </span>
          <div className="min-w-0">
            <p
              className={cn(
                "text-body-sm font-medium",
                item.done ? "text-text-muted" : "text-text",
              )}
            >
              {item.to && !item.done ? (
                <Link to={item.to} className="hover:text-primary hover:underline">
                  {item.label}
                </Link>
              ) : (
                item.label
              )}
              <span className="sr-only">{item.done ? " (done)" : " (to do)"}</span>
            </p>
            <p className="mt-0.5 text-body-sm text-text-muted">{item.hint}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
