/**
 * Timed test (spec §13.5 #14): one question per screen with large answer cards, a counter, the
 * server-timed countdown and a progress bar; every choice saves at once. When the time is up
 * the server scores what was answered. The result shows the score and that it was added to
 * the profile — never which answers were right (that protects the question bank).
 */
import { ArrowLeft, ArrowRight, CircleCheck, Send } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError } from "@/api/client";
import type { Attempt, AttemptResult } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { RadioGroup } from "@/components/ui/Choice";
import { CountdownTimer } from "@/components/ui/CountdownTimer";
import { Card, Skeleton } from "@/components/ui/Display";
import { Alert, ErrorState, PageHeader, Progress, RingProgress } from "@/components/ui/Feedback";
import { ConfirmDialog } from "@/components/ui/Overlay";
import { toast } from "@/components/ui/toast-store";
import { messageFor } from "@/features/auth/errors";
import { useAnswer, useAttempt, useSubmitAttempt } from "@/features/profile/api";
import { formatScore } from "@/lib/format";
import { cn } from "@/lib/cn";

function Result({ attempt, result }: { attempt: Attempt; result: AttemptResult | undefined }) {
  const score = Number(result?.score ?? attempt.score ?? 0);
  return (
    <Card className="mx-auto flex max-w-xl flex-col items-center px-6 py-10 text-center">
      <RingProgress value={score * 100} size={120} label="Your score">
        <span className="text-h3">{formatScore(score)}</span>
      </RingProgress>
      <h2 className="mt-5 text-h4 font-semibold text-text">
        {result
          ? `${String(result.correct)} of ${String(result.total)} correct`
          : "Your test is scored"}
      </h2>
      <p className="mt-2 flex items-center gap-1.5 text-body text-text-muted">
        <CircleCheck className="size-4 text-success" aria-hidden="true" />
        Added to your profile as a verified score.
      </p>
      <p className="mt-1 text-body-sm text-text-muted">You can take this test again in 30 days.</p>
      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <Button asChild>
          <Link to="/dev/profile">See your profile</Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/dev/challenges">Back to challenges</Link>
        </Button>
      </div>
    </Card>
  );
}

function Running({
  attempt,
  onFinished,
}: {
  attempt: Attempt;
  onFinished: (r?: AttemptResult) => void;
}) {
  const [index, setIndex] = useState(0);
  const answer = useAnswer(attempt.id);
  const submit = useSubmitAttempt(attempt.id);
  const offsetMs = useMemo(
    () => new Date(attempt.server_now).getTime() - Date.now(),
    [attempt.server_now],
  );
  const deadline = useMemo(() => new Date(attempt.deadline_at), [attempt.deadline_at]);
  const questions = attempt.questions;
  const question = questions[index];
  const answered = Object.keys(attempt.answers).length;
  const onExpire = useCallback(() => {
    onFinished();
  }, [onFinished]);

  if (!question) return null;
  const choose = (value: string) => {
    answer.mutate(
      { question_id: question.id, choice: Number(value) },
      {
        onError: (e) => {
          if (e instanceof ApiError && e.status === 409) onFinished();
          else toast({ tone: "danger", title: "Answer not saved", description: messageFor(e) });
        },
      },
    );
  };
  const finish = async () => {
    try {
      onFinished(await submit.mutateAsync());
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) onFinished();
      else
        toast({ tone: "danger", title: "The test wasn’t submitted", description: messageFor(e) });
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="sticky top-16 z-10 -mx-4 flex flex-wrap items-center justify-between gap-3 border-b border-border bg-bg/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-lg sm:border">
        <p className="text-body font-semibold text-text tabular">
          Question {index + 1} of {questions.length}
        </p>
        <CountdownTimer deadline={deadline} offsetMs={offsetMs} onExpire={onExpire} />
        <Progress
          className="w-full"
          value={answered}
          max={questions.length}
          label={`${String(answered)} of ${String(questions.length)} answered`}
        />
      </div>
      <Card className="p-5 sm:p-6">
        <RadioGroup
          key={question.id}
          cards
          legend={<span className="text-lead font-semibold text-text">{question.text}</span>}
          value={
            attempt.answers[question.id] !== undefined ? String(attempt.answers[question.id]) : ""
          }
          onValueChange={choose}
          options={question.options.map((text, i) => ({ value: String(i), label: text }))}
        />
      </Card>
      <nav aria-label="Questions" className="flex flex-wrap gap-2">
        {questions.map((q, i) => {
          const done = attempt.answers[q.id] !== undefined;
          return (
            <button
              key={q.id}
              type="button"
              onClick={() => {
                setIndex(i);
              }}
              aria-current={i === index ? "step" : undefined}
              aria-label={`Question ${String(i + 1)}${done ? ", answered" : ""}`}
              className={cn(
                "flex size-11 items-center justify-center rounded-md border text-body-sm font-medium tabular transition-colors duration-fast",
                i === index
                  ? "border-primary text-primary"
                  : "border-border text-text-muted hover:text-text",
                done && "bg-primary-soft",
              )}
            >
              {i + 1}
            </button>
          );
        })}
      </nav>
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
        <Button
          variant="outline"
          disabled={index === 0}
          onClick={() => {
            setIndex(index - 1);
          }}
          icon={<ArrowLeft aria-hidden="true" />}
        >
          Previous
        </Button>
        <div className="flex flex-col-reverse gap-3 sm:flex-row">
          <ConfirmDialog
            destructive={false}
            trigger={
              <Button
                variant={index === questions.length - 1 ? "primary" : "ghost"}
                icon={<Send aria-hidden="true" />}
                loading={submit.isPending}
              >
                Submit test
              </Button>
            }
            title="Submit your answers?"
            description={
              answered < questions.length
                ? `You answered ${String(answered)} of ${String(questions.length)} questions. Unanswered questions count as wrong.`
                : "You answered every question. Your score goes on your profile."
            }
            confirmLabel="Submit test"
            onConfirm={finish}
          />
          {index < questions.length - 1 ? (
            <Button
              onClick={() => {
                setIndex(index + 1);
              }}
              icon={<ArrowRight aria-hidden="true" />}
            >
              Next question
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default function TestPage() {
  const { attemptId = "" } = useParams();
  const attempt = useAttempt(attemptId);
  const [result, setResult] = useState<AttemptResult>();
  const { refetch } = attempt;
  const onFinished = useCallback(
    (r?: AttemptResult) => {
      if (r) setResult(r);
      void refetch(); // an expired attempt is scored by the server on this read
    },
    [refetch],
  );

  const title = attempt.data?.title ?? "Skill test";
  return (
    <>
      <PageHeader
        title={title}
        breadcrumbs={
          <Link
            to="/dev/challenges"
            className="inline-flex min-h-11 items-center gap-1 text-body-sm text-text-muted hover:text-text"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            Skill challenges
          </Link>
        }
      />
      {attempt.isPending ? (
        <div className="mx-auto max-w-3xl space-y-4" aria-hidden="true">
          <Skeleton className="h-16" />
          <Skeleton className="h-72" />
        </div>
      ) : attempt.isError ? (
        <Card>
          {attempt.error instanceof ApiError && attempt.error.status === 404 ? (
            <ErrorState
              title="We couldn’t find this test"
              description="It may belong to another account. Start a test from Skill challenges."
            />
          ) : (
            <ErrorState
              requestId={attempt.error instanceof ApiError ? attempt.error.requestId : null}
              onRetry={() => void attempt.refetch()}
            />
          )}
        </Card>
      ) : attempt.data.submitted_at ? (
        <Result attempt={attempt.data} result={result} />
      ) : (
        <>
          <Alert tone="info" className="mx-auto mb-5 max-w-3xl" title="The clock is on the server">
            Leaving the page doesn’t pause the timer. Answers save as soon as you pick them.
          </Alert>
          <Running attempt={attempt.data} onFinished={onFinished} />
        </>
      )}
    </>
  );
}
