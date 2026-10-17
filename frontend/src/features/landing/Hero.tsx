/** Hero (spec §13.11 #2): headline revealed word by word (40 ms stagger, 8 px rise, blur
 * 4 → 0), subheading after it, two calls to action, a slowly drifting gradient mesh and the
 * 3D talent constellation on the right (below the text on phones). */
import { motion } from "framer-motion";
import { useRef } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/Button";
import { duration, ease, stagger } from "@/design/motion";
import { useMotion } from "@/design/useMotion";
import { HeroVisual } from "./HeroVisual";
import { useActiveWhenVisible } from "./usePauseWhenHidden";

export const HEADLINE = "Plan the project. Hire a fair team. Watch the work. Learn from it.";
/** One sentence per line: the four steps read as a list, never with a lone word. */
const SENTENCES = HEADLINE.split(/(?<=\.)\s/).map((sentence) => sentence.split(" "));
const WORD_COUNT = SENTENCES.flat().length;

export function Hero() {
  const m = useMotion();
  const ref = useRef<HTMLElement>(null);
  const active = useActiveWhenVisible(ref);
  const afterWords = m.reduced ? 0 : WORD_COUNT * stagger.words + duration.slow * 0.6;
  return (
    <section
      ref={ref}
      aria-labelledby="hero-title"
      data-paused={active ? undefined : ""}
      className="relative isolate overflow-hidden pb-16 pt-28 sm:pb-24 lg:pt-36"
    >
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="mesh absolute -left-[15%] -top-[25%] size-[70vmax] rounded-full bg-primary/12 blur-3xl" />
        <div className="mesh mesh-b absolute -right-[20%] top-[5%] size-[60vmax] rounded-full bg-accent/12 blur-3xl" />
        <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent to-bg" />
      </div>
      <div className="mx-auto grid max-w-content items-center gap-12 px-4 sm:px-6 lg:grid-cols-[minmax(0,11fr)_minmax(0,10fr)]">
        <div>
          <motion.h1
            id="hero-title"
            className="text-hero font-semibold tracking-[-0.025em] text-text"
            variants={m.words}
            initial="hidden"
            animate="show"
            aria-label={HEADLINE}
          >
            {SENTENCES.map((words, line) => (
              <span key={words.join(" ")} className="block" aria-hidden="true">
                {words.map((w, i) => (
                  <motion.span
                    key={`${String(line)}-${w}-${String(i)}`}
                    variants={m.word}
                    className="inline-block whitespace-pre"
                  >
                    {w}
                    {i < words.length - 1 ? " " : ""}
                  </motion.span>
                ))}
              </span>
            ))}
          </motion.h1>
          <motion.p
            className="mt-6 max-w-[52ch] text-lead text-text-muted"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: duration.slow, delay: afterWords, ease: ease.standard }}
          >
            DevSync plans your software project with its critical path, forms a balanced team of
            freelance developers, newcomers included, and pays them milestone by milestone.
          </motion.p>
          <motion.div
            className="mt-9 flex flex-col gap-3 sm:flex-row"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{
              duration: duration.slow,
              delay: afterWords + stagger.reveal,
              ease: ease.standard,
            }}
          >
            <Button asChild size="lg" className="glow">
              <Link to="/register?role=client">Hire a team</Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link to="/register?role=developer">Find work</Link>
            </Button>
          </motion.div>
        </div>
        <HeroVisual active={active} />
      </div>
    </section>
  );
}
