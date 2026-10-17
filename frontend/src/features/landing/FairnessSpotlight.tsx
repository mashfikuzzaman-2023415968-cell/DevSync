/**
 * Fairness spotlight (spec §13.11 #7): the newcomer problem and an interactive dial. Moving it
 * from 0 to 2 changes how many places in the example team are kept for newcomers. Until team
 * formation exists (Phase 7) it shows the rule only, no "cost of fairness" figure: homepage
 * numbers must come from a real run (rule 0.2.6, DECISIONS D21).
 */
import { motion } from "framer-motion";
import { useState } from "react";
import { NewcomerBadge } from "@/components/ui/Display";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { orderingSystem } from "@/content/sample";
import { instant, spring } from "@/design/motion";
import { useReducedMotion } from "@/design/preferences";
import { cn } from "@/lib/cn";
import { Reveal, RevealItem } from "./Reveal";

type Dial = "0" | "1" | "2";

const POS = [
  [70, 60],
  [210, 50],
  [230, 170],
  [80, 180],
] as const;

function TeamPreview({ newcomers }: { newcomers: number }) {
  const reduced = useReducedMotion();
  // Newcomer places fill from the last slot backwards, so the change is easy to follow.
  const isNewcomer = (slot: number) => slot >= POS.length - newcomers;
  return (
    <div className="relative">
      <svg viewBox="0 0 300 230" className="h-auto w-full" aria-hidden="true">
        <path
          d="M70 60 210 50 230 170 80 180Z M70 60 230 170 M210 50 80 180"
          fill="none"
          className="stroke-primary/40"
          strokeWidth="2"
        />
        {POS.map(([x, y], slot) => (
          <g key={slot}>
            <motion.circle
              cx={x}
              cy={y}
              r={isNewcomer(slot) ? 30 : 24}
              className={cn(isNewcomer(slot) ? "fill-newcomer/15" : "fill-primary/10")}
              animate={{ r: isNewcomer(slot) ? 30 : 24 }}
              transition={reduced ? instant : spring.drag}
            />
            <motion.circle
              cx={x}
              cy={y}
              r={isNewcomer(slot) ? 15 : 13}
              className={isNewcomer(slot) ? "fill-newcomer" : "fill-primary"}
              animate={{ r: isNewcomer(slot) ? 15 : 13 }}
              initial={false}
              transition={reduced ? instant : spring.drag}
            />
            <text x={x} y={y + 50} textAnchor="middle" className="fill-text-muted text-[12px]">
              {orderingSystem.skills[slot]}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

export function FairnessSpotlight() {
  const [dial, setDial] = useState<Dial>("1");
  const n = Number(dial);
  return (
    <section id="fairness" aria-labelledby="fairness-title" className="bg-surface py-24">
      <div className="mx-auto grid max-w-content items-center gap-14 px-4 sm:px-6 lg:grid-cols-2">
        <Reveal>
          <RevealItem>
            <h2 id="fairness-title" className="text-h1 font-semibold tracking-tight text-text">
              Everyone was a newcomer once
            </h2>
          </RevealItem>
          <RevealItem>
            <p className="mt-5 text-lead text-text-muted">
              On most platforms the developers with the most reviews win most of the work, so new
              developers never get the first job that would earn them a review.
            </p>
          </RevealItem>
          <RevealItem>
            <p className="mt-4 text-lead text-text-muted">
              With DevSync the client turns a dial: keep at least that many places for newcomers who
              passed a skill test. The team is still chosen for quality, and DevSync shows what the
              choice costs.
            </p>
          </RevealItem>
        </Reveal>
        <Reveal>
          <RevealItem className="rounded-xl border border-border bg-bg p-6 shadow-sm sm:p-8">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-body font-semibold text-text" id="dial-label">
                Newcomers at least
              </p>
              <SegmentedControl<Dial>
                label="Newcomers at least"
                value={dial}
                onChange={setDial}
                segments={[
                  { value: "0", label: "0" },
                  { value: "1", label: "1" },
                  { value: "2", label: "2" },
                ]}
              />
            </div>
            <TeamPreview newcomers={n} />
            <div className="flex flex-wrap items-center gap-3" aria-live="polite">
              {n > 0 ? <NewcomerBadge /> : null}
              <p className="text-body-sm text-text">
                {n === 0
                  ? "All four places go to whoever fits best."
                  : `${String(n)} of 4 places ${n === 1 ? "is" : "are"} kept for a newcomer.`}
              </p>
            </div>
            <p className="mt-4 text-caption text-text-muted">
              Example team for the sample “{orderingSystem.title}” project.
            </p>
          </RevealItem>
        </Reveal>
      </div>
    </section>
  );
}
