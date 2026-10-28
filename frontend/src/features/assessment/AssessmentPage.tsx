/**
 * `/dev/assessments/:attemptId` — come back to a role assessment (role assessment spec §6.6,
 * §11.3): after a reload, from another device, or from the "open elsewhere" link. Resuming
 * issues a new window token (any other window stops with "continued in another window"); a
 * finished attempt shows its result.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ApiError } from "@/api/client";
import type { AssessmentResult } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Card, Skeleton } from "@/components/ui/Display";
import { ErrorState, PageHeader } from "@/components/ui/Feedback";
import { resumeAttempt, type TimedAssessment } from "./api";
import { AssessmentRunner, enterFullscreen } from "./AssessmentRunner";
import { ResultView } from "./ResultView";

export default function AssessmentPage() {
  const { attemptId = "" } = useParams();
  const navigate = useNavigate();
  const [attempt, setAttempt] = useState<TimedAssessment | null>(null);
  const [result, setResult] = useState<AssessmentResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [opened, setOpened] = useState(false);

  useEffect(() => {
    let live = true;
    resumeAttempt(attemptId)
      .then((a) => {
        if (live) setAttempt(a);
      })
      .catch((e: unknown) => {
        if (!live) return;
        const r =
          e instanceof ApiError ? (e.details.result as AssessmentResult | undefined) : undefined;
        if (r) setResult(r);
        else setError(e instanceof ApiError ? e : new ApiError(0, null, null));
      });
    return () => {
      live = false;
    };
  }, [attemptId]);

  if (result) {
    return (
      <>
        <PageHeader title="Role assessment" description={result.label} />
        <Card className="p-6">
          <ResultView
            result={result}
            action={
              <Button asChild variant="outline">
                <Link to="/dev/find">Find projects</Link>
              </Button>
            }
          />
        </Card>
      </>
    );
  }
  if (error) {
    return (
      <>
        <PageHeader title="Role assessment" />
        <Card>
          <ErrorState
            title={
              error.status === 404
                ? "We couldn’t find this assessment"
                : "The assessment didn’t open"
            }
            requestId={error.requestId}
            onRetry={() => {
              void navigate(0);
            }}
          />
        </Card>
      </>
    );
  }
  if (!attempt) {
    return (
      <>
        <PageHeader title="Role assessment" />
        <Card className="p-6">
          <Skeleton className="h-32 w-full" />
        </Card>
      </>
    );
  }
  return (
    <>
      <PageHeader title="Role assessment" description={attempt.label} />
      <Card className="flex flex-col items-start gap-3 p-6">
        <p className="text-body text-text">
          Your assessment is still running. The timer didn’t stop while you were away.
        </p>
        <Button
          onClick={() => {
            void enterFullscreen(); // inside the click, as browsers require
            setOpened(true);
          }}
        >
          Continue assessment
        </Button>
      </Card>
      {opened ? (
        <AssessmentRunner
          attempt={attempt}
          closeLabel="Done"
          onClose={(r) => {
            setOpened(false);
            if (r) setResult(r);
          }}
        />
      ) : null}
    </>
  );
}
