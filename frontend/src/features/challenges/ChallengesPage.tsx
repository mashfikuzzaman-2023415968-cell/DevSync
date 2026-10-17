/** Skill challenges (spec §13.5 #14): timed multiple-choice tests that turn into verified
 * evidence on the profile. Coding challenges join in Phase 13. */
import { CalendarClock, ListChecks, Play, RotateCcw } from "lucide-react";
import { useNavigate } from "react-router";
import { ApiError } from "@/api/client";
import type { SkillTest } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Badge, Card, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState, PageHeader, RingProgress } from "@/components/ui/Feedback";
import { ConfirmDialog } from "@/components/ui/Overlay";
import { toast } from "@/components/ui/toast-store";
import { messageFor } from "@/features/auth/errors";
import { useSkillTests, useStartAttempt } from "@/features/profile/api";
import { formatDate, formatScore } from "@/lib/format";

function minutes(seconds: number): string {
  const m = Math.round(seconds / 60);
  return m === 1 ? "1 minute" : `${String(m)} minutes`;
}

function TestCard({ test }: { test: SkillTest }) {
  const navigate = useNavigate();
  const start = useStartAttempt();
  const locked = test.next_attempt_at !== null && test.open_attempt_id === null;

  const begin = async () => {
    try {
      const attempt = await start.mutateAsync(test.id);
      void navigate(`/dev/challenges/test/${attempt.id}`);
    } catch (e) {
      const open = e instanceof ApiError ? e.details.attempt_id : undefined;
      if (typeof open === "string") {
        void navigate(`/dev/challenges/test/${open}`);
        return;
      }
      toast({ tone: "danger", title: "The test didn’t start", description: messageFor(e) });
    }
  };

  return (
    <Card className="flex flex-col p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-body-sm text-text-muted">{test.skill_name}</p>
          <h2 className="mt-0.5 text-h4 font-semibold text-text">{test.title}</h2>
          <p className="mt-1 text-body-sm text-text-muted">
            {test.question_count} questions in {minutes(test.time_limit_seconds)}
          </p>
        </div>
        {test.last_score !== null ? (
          <RingProgress
            value={Number(test.last_score) * 100}
            label={`Your last ${test.skill_name} score`}
          >
            {formatScore(Number(test.last_score))}
          </RingProgress>
        ) : null}
      </div>
      <div className="mt-4 flex flex-1 flex-col justify-end gap-3">
        {test.last_attempt_at ? (
          <p className="text-body-sm text-text-muted">
            Last taken {formatDate(test.last_attempt_at)}
          </p>
        ) : null}
        {test.open_attempt_id ? (
          <Button
            onClick={() => void navigate(`/dev/challenges/test/${test.open_attempt_id ?? ""}`)}
            icon={<RotateCcw aria-hidden="true" />}
          >
            Resume test
          </Button>
        ) : locked ? (
          <Badge tone="neutral" icon={false} className="self-start">
            <CalendarClock className="size-3.5" aria-hidden="true" />
            Available again {formatDate(test.next_attempt_at ?? "")}
          </Badge>
        ) : (
          <ConfirmDialog
            destructive={false}
            trigger={
              <Button
                variant={test.last_score === null ? "primary" : "outline"}
                icon={<Play aria-hidden="true" />}
                loading={start.isPending}
              >
                Start test
              </Button>
            }
            title={`Start the ${test.skill_name} test?`}
            description={`You’ll have ${minutes(test.time_limit_seconds)} for ${String(test.question_count)} questions. The timer starts now and keeps running if you leave the page. Your score goes on your profile, and you can take this test again after 30 days.`}
            confirmLabel="Start the timer"
            onConfirm={begin}
          />
        )}
      </div>
    </Card>
  );
}

export default function ChallengesPage() {
  const tests = useSkillTests();
  return (
    <>
      <PageHeader
        title="Skill challenges"
        description="Pass a timed test to show clients a verified score, even before your first review."
      />
      {tests.isPending ? (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3" aria-hidden="true">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-48 rounded-lg" />
          ))}
        </div>
      ) : tests.isError ? (
        <Card>
          <ErrorState
            requestId={tests.error instanceof ApiError ? tests.error.requestId : null}
            onRetry={() => void tests.refetch()}
          />
        </Card>
      ) : tests.data.length === 0 ? (
        <Card>
          <EmptyState
            icon={<ListChecks />}
            title="No tests yet"
            description="Tests appear here once an admin publishes them."
          />
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {tests.data.map((t) => (
            <TestCard key={t.id} test={t} />
          ))}
        </div>
      )}
    </>
  );
}
