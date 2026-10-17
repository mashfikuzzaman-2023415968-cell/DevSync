/**
 * Feature showcase (spec §13.11 #5): three alternating rows, each with a small looping UI built
 * from the real components and seed sample data (content/sample.ts), so they stay sharp and
 * match the app. Loops pause off screen.
 */
import { motion } from "framer-motion";
import { Check, CircleCheck, Users } from "lucide-react";
import { useRef, type ReactNode } from "react";
import { Badge, Card, RiskChip } from "@/components/ui/Display";
import { Progress } from "@/components/ui/Feedback";
import { inventoryDashboard, orderingSystem, reputationSample } from "@/content/sample";
import { useMotion } from "@/design/useMotion";
import { cn } from "@/lib/cn";
import { formatDays, formatMoney, formatScore } from "@/lib/format";
import { Reveal, RevealItem } from "./Reveal";
import { useLoop } from "./useLoop";
import { useActiveWhenVisible } from "./usePauseWhenHidden";

function Row({
  title,
  text,
  points,
  visual,
  flip,
}: {
  title: string;
  text: string;
  points: string[];
  visual: (active: boolean) => ReactNode;
  flip: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const active = useActiveWhenVisible(ref);
  return (
    <div ref={ref} className="grid items-center gap-10 lg:grid-cols-2 lg:gap-20">
      <Reveal className={cn(flip && "lg:order-2")}>
        <RevealItem>
          <h3 className="text-h2 font-semibold tracking-tight text-text">{title}</h3>
        </RevealItem>
        <RevealItem>
          <p className="mt-4 text-lead text-text-muted">{text}</p>
        </RevealItem>
        <RevealItem>
          <ul className="mt-6 space-y-3">
            {points.map((p) => (
              <li key={p} className="flex gap-3 text-body text-text">
                <Check className="mt-1 size-4 shrink-0 text-primary" aria-hidden="true" />
                {p}
              </li>
            ))}
          </ul>
        </RevealItem>
      </Reveal>
      <div className={cn("relative", flip && "lg:order-1")}>
        <div
          aria-hidden="true"
          className="absolute -inset-3 -z-10 rounded-[28px] bg-gradient-to-br from-primary-soft to-transparent sm:-inset-6"
        />
        {visual(active)}
        <p className="mt-3 text-caption text-text-muted">Example from a sample project</p>
      </div>
    </div>
  );
}

function WhyThisTeam({ active }: { active: boolean }) {
  const m = useMotion();
  const reasons = [
    `Covers every skill: ${orderingSystem.skills.join(", ")}`,
    `Stays within the ${formatMoney(orderingSystem.budgetPaisa)} budget`,
    `Fits the ${formatDays(orderingSystem.deadlineDays)} deadline (the plan needs ${formatDays(orderingSystem.cpm.durationDays)})`,
    "Includes the newcomer you asked for",
  ];
  const step = useLoop(reasons.length + 1, active);
  return (
    <Card className="p-5" aria-hidden="true">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2 text-body font-semibold text-text">
          <Users className="size-5 text-primary" />
          Why this team?
        </p>
      </div>
      <ul className="mt-4 space-y-2">
        {reasons.map((r, i) => (
          <motion.li
            key={r}
            variants={m.listItem}
            initial="hidden"
            animate={i < step ? "show" : "hidden"}
            className="flex items-start gap-2.5 rounded-md bg-surface-2 px-3 py-2.5 text-body-sm text-text"
          >
            <CircleCheck className="mt-0.5 size-4 shrink-0 text-success" />
            {r}
          </motion.li>
        ))}
      </ul>
    </Card>
  );
}

function Monitoring({ active }: { active: boolean }) {
  const step = useLoop(3, active);
  const [risk] = inventoryDashboard.risks;
  return (
    <Card className="p-5" aria-hidden="true">
      <div className="flex items-center justify-between gap-3">
        <p className="text-body font-semibold text-text">{inventoryDashboard.title}</p>
        <Badge tone={step >= 1 ? "warning" : "neutral"}>
          {step >= 1
            ? `Forecast +${String(inventoryDashboard.forecastDays - inventoryDashboard.plannedDays)} days`
            : "On track"}
        </Badge>
      </div>
      <div className="mt-4 space-y-3">
        {inventoryDashboard.milestones.map((ms) => (
          <Progress
            key={ms.name}
            label={ms.name}
            value={ms.progress}
            showValue
            tone={ms.progress === 100 ? "success" : "primary"}
          />
        ))}
      </div>
      <div
        className={cn(
          "mt-4 rounded-md border border-danger/25 bg-danger-bg p-3 transition-opacity duration-slow",
          step >= 2 ? "opacity-100" : "opacity-0",
        )}
      >
        {step >= 2 ? <RiskChip severity={risk.severity}>{risk.title}</RiskChip> : null}
        <p className="mt-1.5 text-body-sm text-text">{risk.detail}</p>
      </div>
    </Card>
  );
}

const ESCROW = ["Not funded", "Funded", "In review", "Paid"] as const;

function Payments({ active }: { active: boolean }) {
  const step = useLoop(ESCROW.length, active);
  const dev = reputationSample[0];
  return (
    <Card className="p-5" aria-hidden="true">
      <p className="text-body font-semibold text-text">Milestone 3: Backend API</p>
      <ol className="mt-4 grid grid-cols-4 gap-2">
        {ESCROW.map((label, i) => (
          <li key={label} className="text-center">
            <span
              className={cn(
                "mx-auto flex size-8 items-center justify-center rounded-full border-2 transition-colors duration-base",
                i < step && "border-primary bg-primary text-on-primary",
                i === step &&
                  (label === "Paid"
                    ? "border-success bg-success text-on-primary"
                    : "border-primary text-primary"),
                i > step && "border-border text-text-subtle",
              )}
            >
              {i < step || (i === step && label === "Paid") ? <Check className="size-4" /> : i + 1}
            </span>
            <span
              className={cn(
                "mt-1.5 block text-caption",
                i <= step ? "text-text" : "text-text-muted",
              )}
            >
              {label}
            </span>
          </li>
        ))}
      </ol>
      <div className="mt-6 border-t border-border pt-4">
        <p className="text-body-sm font-medium text-text">{dev.name}’s reputation</p>
        <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3">
          {(["teamwork", "quality", "punctuality", "communication"] as const).map((k) => (
            <Progress
              key={k}
              label={`${k.charAt(0).toUpperCase()}${k.slice(1)}`}
              value={Number(formatScore(dev.params[k]))}
              showValue
              tone="primary"
            />
          ))}
        </div>
      </div>
    </Card>
  );
}

export function FeatureShowcase() {
  return (
    <section id="features" aria-labelledby="features-title" className="bg-surface py-24">
      <div className="mx-auto max-w-content px-4 sm:px-6">
        <Reveal className="max-w-2xl">
          <RevealItem>
            <h2 id="features-title" className="text-h1 font-semibold tracking-tight text-text">
              Decisions you can see the reasons for
            </h2>
          </RevealItem>
        </Reveal>
        <div className="mt-16 space-y-28">
          <Row
            title="Team formation that explains itself"
            text="DevSync weighs skill, teamwork, speed and cost across every eligible bid, finds the best balance and tells you in plain words why this team won."
            points={[
              "Sealed bids, so nobody undercuts by peeking",
              "Every developer who wasn’t picked can see why",
              "Check the result against the exact best team",
            ]}
            visual={(active) => <WhyThisTeam active={active} />}
            flip={false}
          />
          <Row
            title="Monitoring and early warnings"
            text="Progress, check-ins and the critical path add up to a forecast, so you hear about a late milestone while there’s still time to act."
            points={[
              "Deadline impact in days, not vague colours",
              "Risks come with what to do next",
              "No screenshots, keyloggers or tracking",
            ]}
            visual={(active) => <Monitoring active={active} />}
            flip
          />
          <Row
            title="Milestone payments and a reputation built on real work"
            text="Escrow protects both sides. Approved milestones release payment, and the project’s evidence updates each developer’s reputation."
            points={[
              "Pay only for approved work",
              "Fair payment splits inside the team",
              "Reviews checked for fakes and revenge",
            ]}
            visual={(active) => <Payments active={active} />}
            flip={false}
          />
        </div>
      </div>
    </section>
  );
}
