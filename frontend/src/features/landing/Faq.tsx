/** FAQ (spec §13.11 #9). "Is the money real?" says plainly that payments are simulated. */
import { Accordion } from "@/components/ui/Disclosure";
import { Reveal, RevealItem } from "./Reveal";

export const FAQ = [
  {
    id: "free",
    q: "Is it free?",
    a: "Yes. DevSync is a university course project, and there are no fees to sign up, post projects or bid.",
  },
  {
    id: "money",
    q: "Is the money real?",
    a: "No. Wallets, escrow and payouts are simulated so the whole flow can be shown safely. No real payment is ever taken or sent.",
  },
  {
    id: "teams",
    q: "How are teams chosen?",
    a: "Bids that can’t meet the project’s needs are filtered out first, with the reason shown. DevSync then searches for the team with the best balance of skill, teamwork, speed and cost within your budget and deadline, and explains its choice.",
  },
  {
    id: "newcomers",
    q: "How do newcomers get selected?",
    a: "A client can keep a number of team places for newcomers. Newcomers qualify through a timed skill test, so they’re judged on what they can do rather than on reviews they haven’t had the chance to earn.",
  },
  {
    id: "monitoring",
    q: "Is my work monitored?",
    a: "Only the work itself: tasks, check-ins, deliverables and optional GitHub activity. DevSync never records screens, keystrokes or locations.",
  },
  {
    id: "reviews",
    q: "How are fake reviews handled?",
    a: "Reviews are blind until everyone has submitted, weighted by how trustworthy the reviewer is, and checked for patterns such as rating rings and revenge reviews. Suspicious cases go to an administrator.",
  },
] as const;

export function Faq() {
  return (
    <section id="faq" aria-labelledby="faq-title" className="mx-auto max-w-3xl px-4 py-24 sm:px-6">
      <Reveal>
        <RevealItem>
          <h2 id="faq-title" className="text-h1 font-semibold tracking-tight text-text">
            Questions people ask
          </h2>
        </RevealItem>
        <RevealItem className="mt-8">
          <Accordion items={FAQ.map((f) => ({ id: f.id, title: f.q, content: f.a }))} />
        </RevealItem>
      </Reveal>
    </section>
  );
}
