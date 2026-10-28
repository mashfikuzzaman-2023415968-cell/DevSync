/**
 * Role assessments for admins (role assessment spec §12.1): the review queue (flagged first),
 * and one attempt in full — its focus events and connection gaps, per-question correctness and
 * response times, the result — with **Void** (needs a fresh authenticator code, a reason; the
 * developer may retake at once and bids relying on it are re-evaluated) and **Mark reviewed**.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleX, Flag } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError, api } from "@/api/client";
import type { AssessmentDetail, FlaggedAssessment } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { Alert, EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { Field, FormField, Textarea } from "@/components/ui/Field";
import { Dialog } from "@/components/ui/Overlay";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { toast } from "@/components/ui/toast-store";
import { formatDateTime } from "@/lib/format";

const keys = {
  list: (flagged: string) => ["admin-assessments", flagged] as const,
  detail: (id: string) => ["admin-assessment", id] as const,
};

function outcome(a: FlaggedAssessment): {
  label: string;
  tone: "success" | "warning" | "danger" | "neutral";
} {
  if (a.voided) return { label: "Voided", tone: "neutral" };
  if (!a.submitted_at) return { label: "In progress", tone: "neutral" };
  if (a.terminated_reason === "FOCUS_LIMIT") return { label: "Ended (left twice)", tone: "danger" };
  return a.passed ? { label: "Passed", tone: "success" } : { label: "Not passed", tone: "warning" };
}

export function AssessmentQueue() {
  const [filter, setFilter] = useState("flagged");
  const list = useQuery({
    queryKey: keys.list(filter),
    queryFn: () =>
      api<FlaggedAssessment[]>(`/admin/assessments${filter === "flagged" ? "?flagged=true" : ""}`),
  });
  return (
    <>
      <PageHeader
        title="Role assessments"
        description="Attempts that ended under the two-leave rule or lost connection for long are flagged for a look."
      />
      <div className="mb-4">
        <SegmentedControl
          label="Which attempts"
          value={filter}
          onChange={setFilter}
          segments={[
            { value: "flagged", label: "Flagged" },
            { value: "all", label: "All" },
          ]}
        />
      </div>
      {list.isPending ? (
        <Skeleton className="h-48 w-full rounded-lg" />
      ) : list.isError ? (
        <Card>
          <ErrorState
            requestId={list.error instanceof ApiError ? list.error.requestId : null}
            onRetry={() => void list.refetch()}
          />
        </Card>
      ) : list.data.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Flag className="size-6" aria-hidden="true" />}
            title={filter === "flagged" ? "Nothing flagged" : "No role assessments yet"}
            description="Attempts appear here as newcomers take role assessments."
          />
        </Card>
      ) : (
        <ul className="flex flex-col gap-3">
          {list.data.map((a) => {
            const o = outcome(a);
            return (
              <li key={a.attempt_id}>
                <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
                  <div className="min-w-0">
                    <p className="font-medium text-text">{a.candidate_name}</p>
                    <p className="truncate text-body-sm text-text-muted">{a.label}</p>
                    <p className="text-caption text-text-muted">
                      Started {formatDateTime(a.started_at)}; left the page {a.focus_leaves}{" "}
                      {a.focus_leaves === 1 ? "time" : "times"}
                      {a.reviewed_at ? "; reviewed" : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge tone={o.tone}>{o.label}</Badge>
                    {a.score !== null ? (
                      <span className="tabular font-semibold">{a.score}</span>
                    ) : null}
                    <Button asChild variant="outline" size="sm">
                      <Link to={`/admin/assessments/${a.attempt_id}`}>Open</Link>
                    </Button>
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}

function VoidDialog({ attemptId, onDone }: { attemptId: string; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [code, setCode] = useState("");
  const voidIt = useMutation({
    meta: { inlineErrors: true },
    mutationFn: async () => {
      await api<unknown>("/auth/step-up", { method: "POST", body: { code } });
      return api<{ bids_affected: number }>(`/admin/assessments/${attemptId}/void`, {
        method: "POST",
        body: { reason: reason.trim() },
      });
    },
    onSuccess: (r) => {
      setOpen(false);
      toast({
        tone: "success",
        title: "Assessment voided",
        description:
          r.bids_affected > 0
            ? `${String(r.bids_affected)} bid${r.bids_affected === 1 ? "" : "s"} re-evaluated; the developer was told.`
            : "The developer can take it again now.",
      });
      onDone();
    },
  });
  const ready = reason.trim().length >= 20 && /^\d{6}$/.test(code);
  return (
    <Dialog
      open={open}
      onOpenChange={setOpen}
      trigger={<Button variant="destructive">Void result</Button>}
      title="Void this result"
      description="The result stops counting, bids relying on it are re-evaluated, and the developer can retake at once."
      footer={
        <>
          <Button
            variant="outline"
            onClick={() => {
              setOpen(false);
            }}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={!ready}
            loading={voidIt.isPending}
            onClick={() => {
              voidIt.mutate();
            }}
          >
            Void result
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <FormField label="Reason" hint="At least 20 characters; kept in the audit log.">
          {(a11y) => (
            <Textarea
              {...a11y}
              value={reason}
              maxLength={500}
              rows={3}
              onChange={(e) => {
                setReason(e.target.value);
              }}
            />
          )}
        </FormField>
        <Field
          label="Authenticator code"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          value={code}
          onChange={(e) => {
            setCode(e.target.value.replace(/\D/g, ""));
          }}
        />
        {voidIt.error ? (
          <Alert tone="danger" title="Not voided">
            {voidIt.error instanceof ApiError ? voidIt.error.message : "Please try again."}
          </Alert>
        ) : null}
      </div>
    </Dialog>
  );
}

export function AssessmentDetailPage() {
  const { attemptId = "" } = useParams();
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: keys.detail(attemptId),
    queryFn: () => api<AssessmentDetail>(`/admin/assessments/${attemptId}`),
  });
  const review = useMutation({
    mutationFn: () => api<unknown>(`/admin/assessments/${attemptId}/review`, { method: "POST" }),
    onSuccess: () => {
      toast({ tone: "success", title: "Marked reviewed" });
      void qc.invalidateQueries({ queryKey: keys.detail(attemptId) });
      void qc.invalidateQueries({ queryKey: ["admin-assessments"] });
    },
  });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: keys.detail(attemptId) });
    void qc.invalidateQueries({ queryKey: ["admin-assessments"] });
  };
  if (detail.isPending) return <Skeleton className="h-64 w-full rounded-lg" />;
  if (detail.isError) {
    return (
      <Card>
        <ErrorState
          requestId={detail.error instanceof ApiError ? detail.error.requestId : null}
          onRetry={() => void detail.refetch()}
        />
      </Card>
    );
  }
  const a = detail.data;
  const o = outcome(a);
  return (
    <>
      <PageHeader title={a.candidate_name} description={a.label}>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            loading={review.isPending}
            disabled={Boolean(a.reviewed_at)}
            onClick={() => {
              review.mutate();
            }}
          >
            {a.reviewed_at ? "Reviewed" : "Mark reviewed"}
          </Button>
          {!a.voided && a.submitted_at ? (
            <VoidDialog attemptId={a.attempt_id} onDone={refresh} />
          ) : null}
        </div>
      </PageHeader>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <Card>
          <CardHeader
            title="Answers"
            description="Correctness and time per question (admins only)."
          />
          <ol className="divide-y divide-border">
            {a.answers.map((q) => (
              <li
                key={q.question_id}
                className="flex flex-wrap items-center gap-3 px-5 py-3 text-body-sm"
              >
                {q.correct ? (
                  <CircleCheck className="size-4 text-success" aria-hidden="true" />
                ) : (
                  <CircleX className="size-4 text-danger" aria-hidden="true" />
                )}
                <span className="font-medium tabular text-text">{q.index + 1}.</span>
                <span className="text-text">{q.competency ?? "—"}</span>
                <span className="text-text-muted">difficulty {q.difficulty}</span>
                <span className="ml-auto text-text-muted tabular">
                  {q.answered_at
                    ? `${q.choice === null ? "skipped" : `option ${"ABCD".charAt(q.choice)}`}, ${String(q.seconds ?? 0)} s`
                    : "not reached"}
                </span>
                <span className="sr-only">{q.correct ? "correct" : "wrong"}</span>
              </li>
            ))}
          </ol>
        </Card>
        <div className="flex flex-col gap-6">
          <Card className="p-5">
            <div className="flex items-center justify-between">
              <Badge tone={o.tone}>{o.label}</Badge>
              <span className="text-h3 font-semibold tabular">{a.score ?? "—"}</span>
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-2 text-body-sm">
              <dt className="text-text-muted">Started</dt>
              <dd>{formatDateTime(a.started_at)}</dd>
              <dt className="text-text-muted">Ended</dt>
              <dd>{a.submitted_at ? formatDateTime(a.submitted_at) : "—"}</dd>
              <dt className="text-text-muted">Left the page</dt>
              <dd className="tabular">{a.focus_leaves}</dd>
              <dt className="text-text-muted">Connection gaps</dt>
              <dd className="tabular">{a.connection_gaps}</dd>
              <dt className="text-text-muted">Extra time</dt>
              <dd className="tabular">{Math.round(a.extra_time_seconds / 60)} min</dd>
            </dl>
            {a.void_reason ? (
              <p className="mt-3 text-body-sm text-text-muted">Voided: {a.void_reason}</p>
            ) : null}
          </Card>
          <Card>
            <CardHeader title="Focus events" />
            {a.focus_events.length ? (
              <ol className="divide-y divide-border">
                {a.focus_events.map((e) => (
                  <li key={String(e.seq)} className="px-5 py-3 text-body-sm">
                    <span className="font-medium text-text">
                      {String(e.type).replaceAll("_", " ").toLowerCase()}
                    </span>
                    <span className="block text-caption text-text-muted">
                      {formatDateTime(String(e.server_at))}
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="px-5 pb-5 text-body-sm text-text-muted">No leaves recorded.</p>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
