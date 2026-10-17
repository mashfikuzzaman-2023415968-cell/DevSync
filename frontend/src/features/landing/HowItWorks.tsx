/**
 * How it works (spec §13.11 #4): five steps. Desktop: a sticky list highlights the active
 * step while the illustration beside it swaps as you scroll (Framer Motion useScroll).
 * Phones: a vertical timeline with each step fading in.
 */
import { AnimatePresence, motion, useInView, useMotionValueEvent, useScroll } from "framer-motion";
import { useRef, useState, type ComponentType } from "react";
import { useMotion } from "@/design/useMotion";
import { cn } from "@/lib/cn";
import {
  LearnIllustration,
  PayIllustration,
  PlanIllustration,
  TeamIllustration,
  WorkIllustration,
} from "./Illustrations";
import { Reveal, RevealItem } from "./Reveal";

interface StepInfo {
  title: string;
  text: string;
  Art: ComponentType;
}

export const STEPS: StepInfo[] = [
  {
    title: "Plan",
    text: "Split the work into milestones with dependencies. DevSync finds the critical path and the slack before anyone bids.",
    Art: PlanIllustration,
  },
  {
    title: "Form a fair team",
    text: "Sealed bids are filtered, then a balanced team is chosen on skill, teamwork, time and cost, with room for the newcomers you ask for.",
    Art: TeamIllustration,
  },
  {
    title: "Work",
    text: "The team lead plans tasks and the team posts weekly check-ins. You watch progress and risks, never anyone’s screen.",
    Art: WorkIllustration,
  },
  {
    title: "Pay by milestone",
    text: "Money waits in escrow for each milestone and is released when you approve the work.",
    Art: PayIllustration,
  },
  {
    title: "Learn from it",
    text: "Reviews, punctuality and teamwork from the real project update each developer’s reputation for the next team.",
    Art: LearnIllustration,
  },
];

function StepNumber({ n, active }: { n: number; active: boolean }) {
  return (
    <span
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-full text-body-sm font-semibold tabular transition-colors duration-base",
        active ? "bg-primary text-on-primary" : "bg-surface-2 text-text-muted",
      )}
    >
      {n}
    </span>
  );
}

function DesktopSteps() {
  const ref = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const m = useMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  useMotionValueEvent(scrollYProgress, "change", (v) => {
    setActive(Math.min(STEPS.length - 1, Math.max(0, Math.floor(v * STEPS.length))));
  });
  const step = STEPS[active] ?? STEPS[0];
  const Art = step?.Art ?? PlanIllustration;
  return (
    <div ref={ref} className="relative hidden h-[300vh] lg:block">
      <div className="sticky top-24 grid min-h-[calc(100dvh-8rem)] grid-cols-[minmax(0,5fr)_minmax(0,7fr)] items-center gap-16">
        <ol className="space-y-2">
          {STEPS.map((s, i) => (
            <li
              key={s.title}
              aria-current={i === active ? "step" : undefined}
              className={cn(
                "rounded-lg border p-5 transition-[background-color,border-color,opacity] duration-base",
                i === active
                  ? "border-border bg-surface shadow-sm"
                  : "border-transparent opacity-60",
              )}
            >
              <div className="flex items-start gap-4">
                <StepNumber n={i + 1} active={i === active} />
                <div>
                  <h3 className="text-h4 font-semibold text-text">{s.title}</h3>
                  <p
                    className={cn("mt-1 text-body text-text-muted", i !== active && "line-clamp-1")}
                  >
                    {s.text}
                  </p>
                </div>
              </div>
            </li>
          ))}
        </ol>
        <div className="rounded-xl border border-border bg-surface p-8 shadow-md">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={active} variants={m.swap} initial="hidden" animate="show" exit="exit">
              <Art />
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

/** Mounts the illustration when it scrolls into view, so it animates where it is seen. */
function InViewArt({ Art }: { Art: ComponentType }) {
  const ref = useRef<HTMLDivElement>(null);
  const seen = useInView(ref, { once: true, amount: 0.3 });
  return (
    <div ref={ref} className="aspect-[380/230]">
      {seen ? <Art /> : null}
    </div>
  );
}

function MobileSteps() {
  return (
    <ol className="relative space-y-10 border-l border-border pl-8 lg:hidden">
      {STEPS.map((s, i) => (
        <li key={s.title} className="relative">
          <span className="absolute -left-[49px] top-0">
            <StepNumber n={i + 1} active />
          </span>
          <Reveal>
            <RevealItem>
              <h3 className="text-h4 font-semibold text-text">{s.title}</h3>
              <p className="mt-1 text-body text-text-muted">{s.text}</p>
            </RevealItem>
            <RevealItem className="mt-4 rounded-lg border border-border bg-surface p-4">
              <InViewArt Art={s.Art} />
            </RevealItem>
          </Reveal>
        </li>
      ))}
    </ol>
  );
}

export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      aria-labelledby="how-title"
      className="mx-auto max-w-content px-4 py-24 sm:px-6"
    >
      <Reveal className="max-w-2xl">
        <RevealItem>
          <h2 id="how-title" className="text-h1 font-semibold tracking-tight text-text">
            One loop, from plan to reputation
          </h2>
        </RevealItem>
        <RevealItem>
          <p className="mt-4 text-lead text-text-muted">
            Everything about a project lives in one place, and what happens in it makes the next
            team better.
          </p>
        </RevealItem>
      </Reveal>
      <div className="mt-14">
        <DesktopSteps />
        <MobileSteps />
      </div>
    </section>
  );
}
