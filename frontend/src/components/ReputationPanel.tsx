/**
 * ReputationPanel (spec §13.3 domain composites, §13.5 #16): a developer's six reputation
 * parameters with plain labels, competency and performance, and "what this means" accordions.
 *
 * Values arrive as 0–1 decimal strings and are shown 0–100 (§13.8 #4). The parameters are
 * grouped by what they feed: competency (expertise, communication), performance (quality,
 * client diversity, punctuality) and teamwork, which team formation uses on its own. Paper
 * symbols appear only inside the "How it’s calculated" accordion (§13.10). A developer with no
 * record yet (another user's newcomer) shows "Building a record" instead of empty meters.
 */
import { Sparkles } from "lucide-react";
import type { DeveloperReputation } from "@/api/types";
import { Accordion } from "@/components/ui/Disclosure";
import { Progress } from "@/components/ui/Feedback";
import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/format";
import {
  COMPETENCY_PARTS,
  PARAMETER_BY_KEY,
  PARAMETERS,
  PERFORMANCE_PARTS,
  toNumber,
  type ParameterKey,
} from "@/lib/reputation";

interface Props {
  reputation: DeveloperReputation;
  /** Show the "what this means" accordions (the full page); profiles keep it compact. */
  showEvidence?: boolean;
  className?: string;
}

function Meter({ name, value }: { name: ParameterKey; value: number }) {
  const info = PARAMETER_BY_KEY[name];
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-body-sm">
        <span className="text-text">{info.label}</span>
        <span className="font-semibold tabular text-text">{formatScore(value)}</span>
      </div>
      <Progress value={value * 100} label={`${info.label} ${formatScore(value)} of 100`} />
    </div>
  );
}

function Group({
  title,
  description,
  score,
  parts,
  values,
}: {
  title: string;
  description: string;
  score: number | null;
  parts: readonly ParameterKey[];
  values: Record<ParameterKey, number | null>;
}) {
  return (
    <section aria-labelledby={`rep-${title}`} className="min-w-0">
      <div className="flex items-baseline justify-between gap-3">
        <h3 id={`rep-${title}`} className="text-body font-semibold text-text">
          {title}
        </h3>
        {score !== null ? (
          <p className="text-h4 font-semibold tabular text-text">{formatScore(score)}</p>
        ) : null}
      </div>
      <p className="mt-0.5 text-body-sm text-text-muted">{description}</p>
      <div className="mt-4 space-y-4">
        {parts.map((key) => {
          const v = values[key];
          return v === null ? null : <Meter key={key} name={key} value={v} />;
        })}
      </div>
    </section>
  );
}

export function ReputationPanel({ reputation, showEvidence = false, className }: Props) {
  const values = Object.fromEntries(
    PARAMETERS.map((p) => [p.key, toNumber(reputation.parameters[p.key])]),
  ) as Record<ParameterKey, number | null>;
  const competency = toNumber(reputation.competency);
  const performance = toNumber(reputation.performance);

  if (competency === null || performance === null) {
    return (
      <div className={cn("flex items-start gap-3 rounded-lg bg-newcomer-bg p-4", className)}>
        <Sparkles className="mt-0.5 size-5 shrink-0 text-newcomer" aria-hidden="true" />
        <div>
          <p className="text-body font-semibold text-text">Building a record</p>
          <p className="mt-0.5 text-body-sm text-text-muted">
            This developer hasn’t completed a project on DevSync yet, so there’s no reputation to
            show. Newcomers are judged on their role assessment results instead.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={className}>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-8 md:grid-cols-2">
        <Group
          title="Competency"
          description="What you can do: expertise and communication."
          score={competency}
          parts={COMPETENCY_PARTS}
          values={values}
        />
        <Group
          title="Performance"
          description="How past projects went: quality, client diversity and punctuality."
          score={performance}
          parts={PERFORMANCE_PARTS}
          values={values}
        />
      </div>
      {values.xm !== null ? (
        <div className="mt-8 border-t border-border pt-6">
          <Group
            title="Teamwork"
            description="How you work with teammates. Team formation weighs it on its own."
            score={null}
            parts={["xm"]}
            values={values}
          />
        </div>
      ) : null}
      {showEvidence ? (
        <div className="mt-6 border-t border-border">
          <Accordion
            items={[
              ...PARAMETERS.map((p) => ({
                id: p.key,
                title: `What ${p.label.toLowerCase()} means`,
                content: (
                  <>
                    <p>{p.means}</p>
                    <p className="mt-2">
                      <span className="font-medium text-text">What raises it: </span>
                      {p.grows}
                    </p>
                  </>
                ),
              })),
              {
                id: "formula",
                title: "How it’s calculated",
                content: (
                  <>
                    <p>
                      DevSync uses the reputation model of Akter et al. (2023). Competency C
                      combines expertise ω and communication X; performance P combines quality β,
                      client diversity μ and punctuality T. Each project updates the values, and no
                      single project can move communication, teamwork or quality by more than a
                      fixed limit, so one unusual project can’t swing your reputation.
                    </p>
                    <ul className="mt-2 list-disc pl-5">
                      {PARAMETERS.map((p) => (
                        <li key={p.key}>
                          {p.label} = {p.symbol}
                        </li>
                      ))}
                    </ul>
                  </>
                ),
              },
            ]}
          />
        </div>
      ) : null}
    </div>
  );
}
