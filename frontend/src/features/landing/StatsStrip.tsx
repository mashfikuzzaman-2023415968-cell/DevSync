/** Trust and stats strip (spec §13.11 #3): live numbers that count up once in view; with no
 * numbers yet (new install), only the research line shows, never zeros. */
import { GraduationCap } from "lucide-react";
import { useCountUp } from "@/components/ui/useCountUp";
import { formatCount, formatPercent } from "@/lib/format";
import { usePublicStats, type PublicStats } from "./api";

interface Stat {
  key: keyof PublicStats;
  label: string;
  format: (v: number) => string;
}

const STATS: Stat[] = [
  { key: "projects_planned", label: "projects planned", format: (v) => formatCount(Math.round(v)) },
  { key: "developers", label: "developers", format: (v) => formatCount(Math.round(v)) },
  { key: "newcomers_hired", label: "newcomers hired", format: (v) => formatCount(Math.round(v)) },
  { key: "on_time_rate", label: "milestones on time", format: (v) => formatPercent(v) },
];

function Figure({ stat, value }: { stat: Stat; value: number }) {
  const [ref, shown] = useCountUp<HTMLParagraphElement>(value);
  return (
    <div>
      <p
        ref={ref}
        data-volatile=""
        className="text-h2 font-semibold tabular tracking-tight text-text"
      >
        <span aria-hidden="true">{stat.format(shown)}</span>
        <span className="sr-only">{stat.format(value)}</span>
      </p>
      <p className="mt-1 text-body-sm text-text-muted">{stat.label}</p>
    </div>
  );
}

export function StatsStrip() {
  const stats = usePublicStats();
  const shown = STATS.flatMap((s) => {
    const v = stats.data?.[s.key];
    return typeof v === "number" && v > 0 ? [{ stat: s, value: v }] : [];
  });
  return (
    <section aria-label="DevSync in numbers" className="border-y border-border bg-surface">
      {/* The row keeps the height of the numbers so they never push the page down (CLS). */}
      <div className="mx-auto flex max-w-content flex-col gap-8 px-4 py-10 sm:px-6 lg:min-h-[9rem] lg:flex-row lg:items-center lg:justify-between">
        {shown.length ? (
          <div className="grid grid-cols-2 gap-8 sm:flex sm:gap-14">
            {shown.map(({ stat, value }) => (
              <Figure key={stat.key} stat={stat} value={value} />
            ))}
          </div>
        ) : null}
        <p className="flex items-center gap-3 text-body-sm text-text-muted">
          <GraduationCap className="size-5 shrink-0 text-primary" aria-hidden="true" />
          Based on published research from the University of Dhaka.
        </p>
      </div>
    </section>
  );
}
