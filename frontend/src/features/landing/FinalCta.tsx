/** Final call to action (spec §13.11 #10): a full-width brand-gradient band; a subtle shimmer
 * crosses the primary button every 6 seconds. */
import { Link } from "react-router";
import { Button } from "@/components/ui/Button";
import { Reveal, RevealItem } from "./Reveal";

export function FinalCta() {
  return (
    <section aria-labelledby="cta-title" className="px-4 pb-24 sm:px-6">
      <Reveal className="relative mx-auto max-w-content overflow-hidden rounded-xl bg-gradient-to-br from-primary via-primary-hover to-accent px-6 py-16 text-center sm:px-12">
        <div
          aria-hidden="true"
          className="absolute -right-24 -top-24 size-80 rounded-full bg-white/10 blur-2xl"
        />
        <RevealItem>
          <h2 id="cta-title" className="text-h1 font-semibold tracking-tight text-on-primary">
            Ready to build your next project?
          </h2>
        </RevealItem>
        <RevealItem>
          <p className="mx-auto mt-4 max-w-xl text-lead text-on-primary/85">
            Plan it in minutes and meet a team you can see the reasons for.
          </p>
        </RevealItem>
        <RevealItem className="mt-9 flex flex-col justify-center gap-3 sm:flex-row">
          <Button asChild size="lg" className="sheen bg-surface text-primary hover:bg-surface">
            <Link to="/register?role=client">Hire a team</Link>
          </Button>
          <Button
            asChild
            size="lg"
            variant="outline"
            className="border-on-primary/40 bg-transparent text-on-primary hover:border-on-primary hover:bg-white/10"
          >
            <Link to="/register?role=developer">Find work</Link>
          </Button>
        </RevealItem>
      </Reveal>
    </section>
  );
}
