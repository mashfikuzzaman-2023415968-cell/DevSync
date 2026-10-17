/** Research credit (spec §13.11 #8): both papers, what DevSync adds, and the supervisor. */
import { BookOpen, ExternalLink } from "lucide-react";
import { Reveal, RevealItem } from "./Reveal";

export function ResearchCredit() {
  return (
    <section
      id="research"
      aria-labelledby="research-title"
      className="mx-auto max-w-content px-4 py-24 sm:px-6"
    >
      <Reveal className="mx-auto max-w-3xl rounded-xl border border-border bg-surface p-6 shadow-sm sm:p-10">
        <RevealItem className="flex items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-full bg-primary-soft text-primary">
            <BookOpen className="size-5" aria-hidden="true" />
          </span>
          <h2 id="research-title" className="text-h3 font-semibold tracking-tight text-text">
            Built on published research
          </h2>
        </RevealItem>
        <RevealItem>
          <p className="mt-5 text-body text-text-muted">
            DevSync implements the reputation model and particle swarm team formation from these
            papers, and extends them with project planning, monitoring, a newcomer minimum chosen by
            the client, evidence-based reputation with fake-review checks and an explanation for
            every decision.
          </p>
        </RevealItem>
        <RevealItem>
          <ul className="mt-6 space-y-4">
            <li className="rounded-lg bg-surface-2 p-4 text-body-sm text-text">
              Akter, S.N., Sinthia, A.K., Roy, P., Razzaque, M.A., Hassan, M.M., Pupo, F., Fortino,
              G. (2023).{" "}
              <cite className="not-italic font-semibold">
                Reputation aware optimal team formation for collaborative software crowdsourcing in
                industry 5.0.
              </cite>{" "}
              Journal of King Saud University – Computer and Information Sciences, 35(8), 101710.{" "}
              <a
                href="https://doi.org/10.1016/j.jksuci.2023.101710"
                className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
                rel="noopener noreferrer nofollow"
                target="_blank"
              >
                Read the paper
                <ExternalLink className="size-3.5" aria-hidden="true" />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </li>
            <li className="rounded-lg bg-surface-2 p-4 text-body-sm text-text">
              Rahman, S.T., Sinthia, A.K., Akter, S.N., Roy, P., Razzaque, M.A. (2021).{" "}
              <cite className="not-italic font-semibold">
                Reputation aware fair worker selection in collaborative software crowdsourcing.
              </cite>{" "}
              3rd International Conference on Sustainable Technologies for Industry 4.0 (STI),
              Dhaka, IEEE, pp. 1–6.
            </li>
          </ul>
        </RevealItem>
        <RevealItem>
          <p className="mt-6 text-body-sm text-text-muted">
            Supervised by Palash Roy, Department of Computer Science and Engineering, University of
            Dhaka.
          </p>
        </RevealItem>
      </Reveal>
    </section>
  );
}
