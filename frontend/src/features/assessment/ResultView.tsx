/**
 * A role assessment result (role assessment spec §6.5, §11.4): the score, passed / not passed /
 * ended early, each competency's score with its weight, the strongest and weakest, and until
 * when a pass counts or when a retake is allowed. Never the correct answers or which questions
 * were right — that would give the bank away.
 */
import { CircleAlert, CircleCheck, CircleX } from "lucide-react";
import type { AssessmentResult } from "@/api/types";
import { Progress, RingProgress } from "@/components/ui/Feedback";
import { formatDate } from "@/lib/format";

const OUTCOME = {
  PASSED: { title: "Passed", Icon: CircleCheck, tone: "text-success" },
  NOT_PASSED: { title: "Not passed", Icon: CircleX, tone: "text-danger" },
  ENDED_EARLY: { title: "Ended early", Icon: CircleAlert, tone: "text-warning" },
  VOIDED: { title: "Voided by an admin", Icon: CircleAlert, tone: "text-warning" },
} as const;

function percent(weightBp: number): string {
  return `${String(Math.round(weightBp / 100))}%`;
}

export function ResultView({
  result,
  action,
}: {
  result: AssessmentResult;
  action?: React.ReactNode;
}) {
  const outcome = OUTCOME[result.outcome];
  const weakest = result.competencies.find((c) => c.name === result.weakest);
  return (
    <section aria-labelledby="result-title" className="mx-auto flex w-full max-w-xl flex-col gap-6">
      <div className="flex flex-col items-center text-center">
        <RingProgress value={result.score} size={128} label="Your score">
          <span className="text-h2 font-semibold tabular">{result.score}</span>
        </RingProgress>
        <h2
          id="result-title"
          className={`mt-4 flex items-center gap-2 text-h3 font-semibold ${outcome.tone}`}
        >
          <outcome.Icon className="size-6" aria-hidden="true" />
          {outcome.title}
        </h2>
        <p className="mt-1 text-body text-text-muted">{result.label}</p>
        <p className="mt-2 text-body-sm text-text-muted">
          {result.outcome === "ENDED_EARLY"
            ? "You left the assessment twice, so it ended. It’s scored but can’t count as a pass."
            : `The pass mark is ${String(result.pass_overall)}, with no heavy competency under 40.`}
        </p>
      </div>

      <div>
        <h3 className="text-body font-semibold text-text">By competency</h3>
        <ul className="mt-3 flex flex-col gap-3">
          {result.competencies.map((c) => (
            <li key={c.code}>
              <div className="flex items-baseline justify-between gap-3 text-body-sm">
                <span className="text-text">
                  {c.name}{" "}
                  <span className="text-text-muted">({percent(c.weight_bp)} of the score)</span>
                </span>
                <span className="font-semibold tabular text-text">{c.score}</span>
              </div>
              <Progress
                className="mt-1.5"
                value={c.score}
                max={100}
                label={`${c.name}: ${String(c.score)} out of 100`}
              />
            </li>
          ))}
        </ul>
        {result.strongest && result.weakest ? (
          <p className="mt-4 text-body-sm text-text-muted">
            Strongest: <span className="font-medium text-text">{result.strongest}</span>. Weakest:{" "}
            <span className="font-medium text-text">{result.weakest}</span>.
          </p>
        ) : null}
      </div>

      <div className="rounded-lg border border-border bg-surface-2 p-4 text-body-sm text-text">
        {result.passed && result.valid_until ? (
          <p>
            This result counts for roles like this one until {formatDate(result.valid_until)}. It
            shows your competency; it doesn’t count as completed work.
          </p>
        ) : result.next_allowed_at ? (
          <p>
            You can retake this assessment on {formatDate(result.next_allowed_at)}.
            {weakest
              ? ` Practice tests can help with ${weakest.name.toLowerCase()} until then.`
              : ""}
          </p>
        ) : (
          <p>You can take this assessment again now.</p>
        )}
      </div>
      {action ? <div className="flex justify-center">{action}</div> : null}
    </section>
  );
}
