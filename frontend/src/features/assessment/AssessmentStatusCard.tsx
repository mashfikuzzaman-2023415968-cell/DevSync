/**
 * The role assessment in the bid sheet (role assessment spec §8.1, §11.2): whether a newcomer
 * needs one for the chosen role, what it covers and why, where they stand, and the way in.
 * The bid's submit button reads `canBid` from the same status (the server enforces it anyway).
 */
import { ChevronDown, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import type { AssessmentStatus } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Badge, Card, Skeleton } from "@/components/ui/Display";
import { Alert } from "@/components/ui/Feedback";
import { formatDate } from "@/lib/format";
import { resumeAttempt, useSlotAssessment, type TimedAssessment } from "./api";
import { ConsentDialog } from "./ConsentDialog";

/** Whether this status lets the bid be placed (§11.2). */
export function canBid(status: AssessmentStatus | undefined): boolean {
  if (!status) return false;
  if (status.status === "NOT_REQUIRED" || status.status === "PASSED") return true;
  return status.status === "FALLBACK_PRACTICE" && Boolean(status.fallback?.passes);
}

function percent(weightBp: number): string {
  return `${String(Math.round(weightBp / 100))}%`;
}

function Required({ status, onStart }: { status: AssessmentStatus; onStart: () => void }) {
  const [why, setWhy] = useState(false);
  const bp = status.blueprint;
  if (!bp) return null;
  const minutes = Math.round((bp.time_limit_seconds + bp.extra_time_seconds) / 60);
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="flex items-center gap-2 text-body font-semibold text-text">
          <ShieldCheck className="size-5 text-primary" aria-hidden="true" />
          Role assessment required
        </h3>
        <p className="mt-1 text-body-sm text-text-muted">{status.message}</p>
      </div>
      <ul className="flex flex-wrap gap-1.5" aria-label="What it covers">
        {bp.competencies.map((c) => (
          <li key={c.code}>
            <Badge tone="neutral">
              {c.name} <span className="tabular text-text-muted">{percent(c.weight_bp)}</span>
            </Badge>
          </li>
        ))}
      </ul>
      <div>
        <button
          type="button"
          className="inline-flex min-h-11 items-center gap-1 text-body-sm font-medium text-primary"
          aria-expanded={why}
          aria-controls="assessment-reasons"
          onClick={() => {
            setWhy((v) => !v);
          }}
        >
          Why these?
          <ChevronDown
            className={`size-4 transition-transform duration-fast ${why ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </button>
        {why ? (
          <ul id="assessment-reasons" className="mt-2 flex flex-col gap-2 text-body-sm">
            {bp.competencies.map((c) => (
              <li key={c.code}>
                <span className="font-medium text-text">{c.name}:</span>{" "}
                <span className="text-text-muted">{c.reasons.join("; ")}.</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-body-sm text-text-muted tabular">
          {bp.question_count} questions, {minutes} minutes, pass mark {bp.pass_overall}
        </p>
        <Button onClick={onStart}>Start assessment</Button>
      </div>
    </div>
  );
}

export function AssessmentStatusCard({
  projectId,
  slotId,
  onRun,
}: {
  projectId: string;
  slotId: string;
  /** Opens the runner over the bid sheet. */
  onRun: (attempt: TimedAssessment) => void;
}) {
  const query = useSlotAssessment(projectId, slotId);
  const [consent, setConsent] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const status = query.data;

  if (query.isLoading) return <Skeleton className="h-24 w-full" />;
  if (query.isError || !status) {
    return (
      <Alert tone="danger" title="We couldn’t check the role assessment">
        {query.error instanceof ApiError ? query.error.message : "Please try again."}
      </Alert>
    );
  }

  const resume = (attemptId: string) => {
    setResumeError(null);
    resumeAttempt(attemptId)
      .then(onRun)
      .catch((e: unknown) => {
        setResumeError(e instanceof ApiError ? e.message : "Please try again.");
      });
  };

  let body: React.ReactNode;
  switch (status.status) {
    case "NOT_REQUIRED":
      return null;
    case "REQUIRED":
      body = (
        <Required
          status={status}
          onStart={() => {
            setConsent(true);
          }}
        />
      );
      break;
    case "IN_PROGRESS":
      body = (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-body text-text">{status.message}</p>
          <Button
            onClick={() => {
              if (status.attempt_id) resume(status.attempt_id);
            }}
          >
            Resume assessment
          </Button>
        </div>
      );
      break;
    case "OPEN_ELSEWHERE":
      return (
        <Alert tone="info" title="Another assessment is open">
          Finish or let your other assessment expire first.{" "}
          {status.open_elsewhere ? (
            <Link
              className="font-medium text-primary underline"
              to={`/dev/assessments/${status.open_elsewhere}`}
            >
              Go to it
            </Link>
          ) : null}
        </Alert>
      );
    case "PASSED":
      return (
        <Alert
          tone="success"
          title={`Role assessment passed: ${String(status.result?.score ?? "")}`}
        >
          {status.result?.valid_until
            ? `It counts for this role until ${formatDate(status.result.valid_until)}. You can place your bid.`
            : "You can place your bid."}
        </Alert>
      );
    case "RETAKE_LOCKED":
      return (
        <Alert
          tone="warning"
          title={`Role assessment: ${String(status.result?.score ?? "")}, not passed`}
        >
          {status.next_allowed_at
            ? `You can retake it on ${formatDate(status.next_allowed_at)}. Practice tests can help until then.`
            : "You can retake it later."}
        </Alert>
      );
    case "FALLBACK_PRACTICE":
      return (
        <Alert tone="info" title="Practice test result used">
          {status.message}{" "}
          {status.fallback?.passes ? (
            `Your result: ${String(status.fallback.practice_score)}.`
          ) : (
            <Link className="font-medium text-primary underline" to="/dev/challenges">
              Take the {status.fallback?.skill_name ?? ""} practice test
            </Link>
          )}
        </Alert>
      );
    case "CLOSED":
      return (
        <Alert tone="info" title="Bidding has closed for this project">
          {status.message}
        </Alert>
      );
    case "BLOCKED":
      return (
        <Alert tone="warning" title="Before you can bid for this role">
          {status.message}{" "}
          <Link
            className="font-medium text-primary underline"
            to={status.reason === "ACCOUNT_NOT_VERIFIED" ? "/verify" : "/dev/profile"}
          >
            {status.reason === "ACCOUNT_NOT_VERIFIED" ? "Verify your account" : "Edit your profile"}
          </Link>
        </Alert>
      );
  }

  return (
    <Card className="p-5" data-testid="assessment-card">
      {body}
      {resumeError ? (
        <Alert tone="danger" title="The assessment didn’t open" className="mt-3">
          {resumeError}
        </Alert>
      ) : null}
      <ConsentDialog
        open={consent}
        onOpenChange={setConsent}
        projectId={projectId}
        slotId={slotId}
        status={status}
        onStarted={onRun}
      />
    </Card>
  );
}
