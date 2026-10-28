/**
 * The rules, accepted before an attempt starts (role assessment spec §7.1). Full screen is asked
 * for on "Start assessment" itself — browsers only allow it during a click — and where a browser
 * can't (iPhone Safari) the assessment fills the window instead, which the rules say.
 */
import { useState } from "react";
import { ApiError } from "@/api/client";
import type { AssessmentStatus } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Choice";
import { Alert } from "@/components/ui/Feedback";
import { Dialog } from "@/components/ui/Overlay";
import { formatDateTime } from "@/lib/format";
import { messageFor } from "@/features/auth/errors";
import { useStartAssessment, type TimedAssessment } from "./api";
import { enterFullscreen, fullscreenSupported } from "./AssessmentRunner";

export function ConsentDialog({
  open,
  onOpenChange,
  projectId,
  slotId,
  status,
  onStarted,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  slotId: string;
  status: AssessmentStatus;
  onStarted: (attempt: TimedAssessment) => void;
}) {
  const [agreed, setAgreed] = useState(false);
  const start = useStartAssessment(projectId, slotId);
  const bp = status.blueprint;
  const minutes = bp ? Math.round((bp.time_limit_seconds + bp.extra_time_seconds) / 60) : 15;
  const questions = bp?.question_count ?? 12;
  const canFullscreen = fullscreenSupported();

  const begin = () => {
    // Full screen first, inside this click; the attempt starts right after.
    const fullscreen = enterFullscreen();
    start.mutate(
      { consent: true, rules_version: status.rules_version },
      {
        onSuccess: (attempt) => {
          onOpenChange(false);
          onStarted(attempt);
        },
        onError: () => {
          void fullscreen.then((on) => {
            if (on) void document.exitFullscreen().catch(() => undefined);
          });
        },
      },
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title="Before you start"
      description={bp?.label}
      footer={
        <>
          <Button
            variant="outline"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            Not now
          </Button>
          <Button disabled={!agreed} loading={start.isPending} onClick={begin}>
            Start assessment
          </Button>
        </>
      }
    >
      <ul className="flex list-disc flex-col gap-2 pl-5 text-body text-text">
        <li>
          This assessment has {questions} questions and {minutes} minutes in total.
        </li>
        <li>
          Questions appear one at a time. Once you answer or skip a question, you can’t go back.
        </li>
        {canFullscreen ? (
          <li>
            The assessment opens in full screen. Leaving full screen (including pressing Esc),
            switching tabs, windows or apps, or closing or reloading the page counts as leaving.
          </li>
        ) : (
          <li>
            Your browser can’t open full screen, so the assessment fills the window instead.
            Switching tabs or apps, or closing or reloading the page, counts as leaving.
          </li>
        )}
        <li>
          The first time you leave, you’ll get a warning and can continue (the timer keeps running).
        </li>
        <li>
          The second time, the assessment ends. It’s scored but can’t count as a pass, and you can
          retake it after 30 days.
        </li>
        <li>
          We only record when you leave this page. We never record your screen, camera or
          keystrokes.
        </li>
        <li>
          Your result shows your competency for this role. It doesn’t count as completed work.
        </li>
      </ul>
      {status.bidding_closes_soon && status.bidding_deadline ? (
        <Alert tone="warning" title="Bidding closes soon" className="mt-4">
          {`Bidding for this project closes at ${formatDateTime(status.bidding_deadline)}. You may not have time to place your bid after the assessment.`}
        </Alert>
      ) : null}
      {start.error ? (
        <Alert tone="danger" title="The assessment didn’t start" className="mt-4">
          {start.error instanceof ApiError ? start.error.message : messageFor(start.error)}
        </Alert>
      ) : null}
      <div className="mt-5">
        <Checkbox
          label="I understand and agree"
          checked={agreed}
          onCheckedChange={(v) => {
            setAgreed(v === true);
          }}
        />
        <p className="mt-1 text-caption text-text-muted">Rules version {status.rules_version}</p>
      </div>
    </Dialog>
  );
}
