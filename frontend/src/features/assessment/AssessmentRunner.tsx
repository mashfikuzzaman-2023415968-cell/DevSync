/**
 * The role assessment runner (role assessment spec §6, §7, §11.3): a full-screen panel over the
 * bid sheet (the bid draft stays in memory) or the resume page. One question at a time from the
 * server, a countdown from the server's clock, the focus guard, a heartbeat every 15 s, and the
 * screens for a warning, an attempt that ended, one continued in another window, time running
 * out and the result. The panel can't be dismissed while the attempt runs (Escape leaves full
 * screen, which the guard counts — that is disclosed on the consent screen).
 */
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Lock, MonitorX, TriangleAlert, WifiOff } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "@/api/client";
import type { AssessmentQuestion, AssessmentResult, FocusEventResult } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { CountdownTimer } from "@/components/ui/CountdownTimer";
import { Alert } from "@/components/ui/Feedback";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/cn";
import {
  answerQuestion,
  finishAttempt,
  forgetAttemptToken,
  sendHeartbeat,
  type TimedAssessment,
} from "./api";
import { QuestionView } from "./QuestionView";
import { ResultView } from "./ResultView";
import { useFocusGuard } from "./useFocusGuard";

const HEARTBEAT_MS = 15_000;
const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000];
const WARN_AT_SECONDS = 120;
const DANGER_AT_SECONDS = 30;
const ANNOUNCE_AT_SECONDS = [300, 120, 60] as const;

type Phase = "running" | "warning" | "scoring" | "result" | "moved";

export function fullscreenSupported(): boolean {
  return typeof document.documentElement.requestFullscreen === "function";
}

/** Ask for full screen (needs a click or key press); false when refused or unsupported. */
export async function enterFullscreen(): Promise<boolean> {
  if (!fullscreenSupported()) return false;
  try {
    await document.documentElement.requestFullscreen({ navigationUI: "hide" });
    return true;
  } catch {
    return false;
  }
}

function leaveFullscreen() {
  if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
}

function resultFrom(error: unknown): AssessmentResult | null {
  if (error instanceof ApiError) {
    const result = error.details.result as AssessmentResult | undefined;
    if (result) return result;
  }
  return null;
}

/** Steps of the one-way path: answered ones are locked, the current one is outlined. */
function ProgressRail({ index, total }: { index: number; total: number }) {
  return (
    <div className="flex w-full items-center gap-1" aria-hidden="true">
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={cn(
            "h-1.5 flex-1 rounded-full",
            i < index && "bg-primary",
            i === index && "bg-primary-soft ring-1 ring-primary",
            i > index && "bg-surface-2 ring-1 ring-border",
          )}
        />
      ))}
    </div>
  );
}

export function AssessmentRunner({
  attempt,
  onClose,
  closeLabel = "Back to your bid",
}: {
  attempt: TimedAssessment;
  onClose: (result: AssessmentResult | null) => void;
  closeLabel?: string;
}) {
  const [phase, setPhase] = useState<Phase>(attempt.result ? "result" : "running");
  const [question, setQuestion] = useState<AssessmentQuestion | null>(attempt.question ?? null);
  const [index, setIndex] = useState(attempt.current_index);
  const [result, setResult] = useState<AssessmentResult | null>(attempt.result ?? null);
  const [leaves, setLeaves] = useState(attempt.focus_leaves);
  const [busy, setBusy] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [canFullscreen, setCanFullscreen] = useState(fullscreenSupported());
  const deadline = useMemo(() => new Date(attempt.deadline_at), [attempt.deadline_at]);
  const id = attempt.id;
  const open = phase === "running" || phase === "warning";
  const leavesLeft = Math.max(0, attempt.leave_limit - leaves - 1);

  const finished = useCallback(
    (r: AssessmentResult | null) => {
      setResult(r);
      setPhase(r ? "result" : "scoring");
      forgetAttemptToken(id);
      leaveFullscreen();
    },
    [id],
  );
  const scoreNow = useCallback(async () => {
    setPhase("scoring");
    leaveFullscreen();
    for (const delay of [0, ...RETRY_DELAYS_MS]) {
      if (delay) await new Promise((r) => setTimeout(r, delay));
      try {
        finished(await api<AssessmentResult>(`/assessment-attempts/${id}/result`));
        return;
      } catch (error) {
        if (error instanceof ApiError && error.status !== 0 && error.code !== "INVALID_STATE")
          break;
      }
    }
  }, [finished, id]);
  const handleError = useCallback(
    (error: unknown): boolean => {
      if (!(error instanceof ApiError)) return false;
      if (error.code === "ATTEMPT_MOVED") {
        setPhase("moved");
        leaveFullscreen();
        return true;
      }
      const r = resultFrom(error);
      if (r) {
        finished(r);
        return true;
      }
      return false;
    },
    [finished],
  );

  const onFocusResult = useCallback(
    (r: FocusEventResult) => {
      setLeaves(r.focus_leaves);
      if (r.result) finished(r.result);
      else if (r.status === "WARNING") setPhase("warning");
    },
    [finished],
  );
  useFocusGuard({
    attemptId: id,
    enabled: open && question !== null,
    serverLeaves: attempt.focus_leaves,
    debounceMs: 3000,
    fullscreenSupported: canFullscreen,
    onResult: onFocusResult,
    onError: handleError,
  });

  // Heartbeat: keeps the server's gap measurement honest; reports a closed or moved attempt.
  useEffect(() => {
    if (!open) return undefined;
    const beat = () => {
      sendHeartbeat(id, {
        visible: document.visibilityState === "visible",
        fullscreen: document.fullscreenElement !== null,
      })
        .then(() => {
          setReconnecting(false);
        })
        .catch((error: unknown) => {
          if (!handleError(error) && error instanceof ApiError && error.status === 0) {
            setReconnecting(true);
          }
        });
    };
    const timer = window.setInterval(beat, HEARTBEAT_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, [handleError, id, open]);

  const answer = useCallback(
    async (choice: number | null) => {
      if (!question) return;
      setBusy(true);
      for (const delay of [0, ...RETRY_DELAYS_MS]) {
        if (delay) {
          setReconnecting(true);
          await new Promise((r) => setTimeout(r, delay));
        }
        try {
          const r = await answerQuestion(id, { question_id: question.id, choice });
          setReconnecting(false);
          setBusy(false);
          if (r.status === "SCORED" && r.result) finished(r.result);
          else if (r.question) {
            setQuestion(r.question);
            setIndex(r.current_index);
          }
          return;
        } catch (error) {
          if (handleError(error)) {
            setBusy(false);
            return;
          }
          if (!(error instanceof ApiError) || error.status !== 0) break;
        }
      }
      setBusy(false);
    },
    [finished, handleError, id, question],
  );

  const finishEarly = async () => {
    setBusy(true);
    try {
      finished(await finishAttempt(id));
    } catch (error) {
      if (!handleError(error)) setBusy(false);
    }
  };

  const total = attempt.total;
  return (
    <DialogPrimitive.Root open modal>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Content
          aria-describedby={undefined}
          onEscapeKeyDown={(e) => {
            e.preventDefault();
          }}
          onPointerDownOutside={(e) => {
            e.preventDefault();
          }}
          onInteractOutside={(e) => {
            e.preventDefault();
          }}
          className="fixed inset-0 z-50 flex h-dvh flex-col overflow-hidden bg-bg print:hidden"
          data-testid="assessment-runner"
        >
          <header className="border-b border-border bg-surface px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:px-6">
            <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <DialogPrimitive.Title className="truncate text-body-sm font-medium text-text-muted">
                  {attempt.label}
                </DialogPrimitive.Title>
                {open ? (
                  <p className="text-body font-semibold text-text tabular">
                    Question {Math.min(index + 1, total)} of {total}
                  </p>
                ) : null}
              </div>
              {open ? (
                <CountdownTimer
                  deadline={deadline}
                  offsetMs={attempt.clock_offset_ms}
                  warnAt={WARN_AT_SECONDS}
                  dangerAt={DANGER_AT_SECONDS}
                  announceAt={ANNOUNCE_AT_SECONDS}
                  onExpire={() => {
                    void scoreNow();
                  }}
                />
              ) : null}
            </div>
            {open ? (
              <div className="mx-auto mt-3 max-w-3xl">
                <ProgressRail index={index} total={total} />
                <p className="sr-only">
                  {`${String(index)} of ${String(total)} questions answered and locked.`}
                </p>
              </div>
            ) : null}
          </header>

          <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 sm:py-10">
            <div className="mx-auto max-w-3xl">
              {reconnecting ? (
                <Alert tone="warning" title="Reconnecting…" className="mb-4">
                  <span className="inline-flex items-center gap-2">
                    <WifiOff className="size-4" aria-hidden="true" />
                    Your answer is kept; it’s sent as soon as the connection is back.
                  </span>
                </Alert>
              ) : null}
              {phase === "running" && question ? (
                <QuestionView question={question} busy={busy} onAnswer={(c) => void answer(c)} />
              ) : null}
              {phase === "running" && !question ? (
                <p className="text-body text-text-muted">Loading the question…</p>
              ) : null}
              {phase === "scoring" ? (
                <div className="flex flex-col items-center gap-3 py-16 text-center" role="status">
                  <Spinner />
                  <p className="text-lead font-semibold text-text">Time’s up — scoring…</p>
                </div>
              ) : null}
              {phase === "result" && result ? (
                <ResultView
                  result={result}
                  action={
                    <Button
                      onClick={() => {
                        onClose(result);
                      }}
                    >
                      {closeLabel}
                    </Button>
                  }
                />
              ) : null}
              {phase === "moved" ? (
                <div className="flex flex-col items-center gap-3 py-16 text-center">
                  <MonitorX className="size-10 text-text-muted" aria-hidden="true" />
                  <h2 className="text-h3 font-semibold text-text">
                    This assessment continued in another window
                  </h2>
                  <p className="max-w-md text-body text-text-muted">
                    It was opened again on this or another device, so this window has stopped. The
                    timer keeps running there.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => {
                      onClose(null);
                    }}
                  >
                    Close
                  </Button>
                </div>
              ) : null}
            </div>
          </main>

          {open ? (
            <footer className="border-t border-border bg-surface px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-6">
              <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3">
                <p className="flex items-center gap-2 text-body-sm text-text-muted">
                  <Lock className="size-4 shrink-0" aria-hidden="true" />
                  {canFullscreen
                    ? "Leaving full screen or this tab counts as leaving"
                    : "Leaving this tab or app counts as leaving"}{" "}
                  ({leavesLeft === 1 ? "1 warning left" : "no warnings left"}).
                </p>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() => {
                    void finishEarly();
                  }}
                >
                  Finish now
                </Button>
              </div>
            </footer>
          ) : null}

          {phase === "warning" ? (
            <div
              role="alertdialog"
              aria-modal="true"
              aria-labelledby="leave-warning-title"
              className="fixed inset-0 z-50 flex items-center justify-center bg-[rgb(2_6_23/0.55)] p-4"
            >
              <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-lg">
                <h2
                  id="leave-warning-title"
                  className="flex items-center gap-2 text-h4 font-semibold text-text"
                >
                  <TriangleAlert className="size-5 text-warning" aria-hidden="true" />
                  You left the assessment
                </h2>
                <p className="mt-2 text-body text-text-muted">
                  This is your only warning; leaving again will end it. The timer kept running.
                </p>
                <div className="mt-5 flex flex-col gap-3 sm:flex-row-reverse">
                  {canFullscreen ? (
                    <Button
                      onClick={() => {
                        void enterFullscreen().then((ok) => {
                          if (ok) setPhase("running");
                          else setCanFullscreen(false);
                        });
                      }}
                    >
                      Return to full screen
                    </Button>
                  ) : (
                    <Button
                      onClick={() => {
                        setPhase("running");
                      }}
                    >
                      Continue without full screen
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
