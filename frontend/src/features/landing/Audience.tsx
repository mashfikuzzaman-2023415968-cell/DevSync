/** For clients / For developers (spec §13.11 #6): a segmented toggle with a sliding indicator
 * swaps two benefit lists with a cross-fade; each list ends with its call to action. */
import { AnimatePresence, motion } from "framer-motion";
import { Check } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/Button";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useMotion } from "@/design/useMotion";
import { Reveal, RevealItem } from "./Reveal";

type Audience = "clients" | "developers";

const CONTENT: Record<
  Audience,
  { heading: string; points: [string, string][]; cta: string; to: string }
> = {
  clients: {
    heading: "Ship a project without managing a hiring process",
    points: [
      ["Plan in minutes", "Milestones, dependencies and the critical path from a short wizard."],
      [
        "Fair teams within budget",
        "A balanced team that fits your budget and deadline, with reasons.",
      ],
      ["Early delay warnings", "See which milestone threatens the deadline, and by how many days."],
      ["Pay only for approved work", "Escrow per milestone, released when you approve."],
    ],
    cta: "Hire a team",
    to: "/register?role=client",
  },
  developers: {
    heading: "Get picked for what you can do, not how long you’ve been here",
    points: [
      [
        "A fair first chance",
        "Clients can reserve team places for newcomers; a skill test counts.",
      ],
      ["See why you weren’t picked", "The main gap, a hint and the price that would have won."],
      [
        "Reputation from real work",
        "Teamwork, punctuality and quality measured on projects, not just stars.",
      ],
      ["Fair payment splits", "Shares follow the evidence of who did what."],
    ],
    cta: "Find work",
    to: "/register?role=developer",
  },
};

export function AudienceToggle() {
  const [audience, setAudience] = useState<Audience>(() =>
    window.location.hash === "#for-developers" ? "developers" : "clients",
  );
  useEffect(() => {
    const onHash = () => {
      if (window.location.hash === "#for-developers") setAudience("developers");
      if (window.location.hash === "#for-clients") setAudience("clients");
    };
    window.addEventListener("hashchange", onHash);
    return () => {
      window.removeEventListener("hashchange", onHash);
    };
  }, []);
  const m = useMotion();
  const c = CONTENT[audience];
  return (
    <section aria-labelledby="audience-title" className="mx-auto max-w-content px-4 py-24 sm:px-6">
      <span id="for-clients" className="block" aria-hidden="true" />
      <span id="for-developers" className="block" aria-hidden="true" />
      <Reveal className="flex flex-col items-start gap-6 sm:flex-row sm:items-end sm:justify-between">
        <RevealItem>
          <h2 id="audience-title" className="text-h1 font-semibold tracking-tight text-text">
            Built for both sides of the project
          </h2>
        </RevealItem>
        <RevealItem>
          <SegmentedControl<Audience>
            label="Show benefits for"
            value={audience}
            onChange={setAudience}
            segments={[
              { value: "clients", label: "For clients" },
              { value: "developers", label: "For developers" },
            ]}
          />
        </RevealItem>
      </Reveal>
      <div
        className="mt-10 rounded-xl border border-border bg-surface p-6 shadow-sm sm:p-10"
        aria-live="polite"
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={audience} variants={m.swap} initial="hidden" animate="show" exit="exit">
            <h3 className="text-h3 font-semibold tracking-tight text-text">{c.heading}</h3>
            <ul className="mt-8 grid gap-6 sm:grid-cols-2">
              {c.points.map(([title, text]) => (
                <li key={title} className="flex gap-4">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary">
                    <Check className="size-4" aria-hidden="true" />
                  </span>
                  <span>
                    <span className="block text-body font-semibold text-text">{title}</span>
                    <span className="mt-0.5 block text-body text-text-muted">{text}</span>
                  </span>
                </li>
              ))}
            </ul>
            <Button asChild size="lg" className="mt-10">
              <Link to={c.to}>{c.cta}</Link>
            </Button>
          </motion.div>
        </AnimatePresence>
      </div>
    </section>
  );
}
