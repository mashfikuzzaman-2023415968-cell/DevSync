/**
 * Check-ins tab `/w/:projectId/check-ins` (spec §13.5 #34; D145): this week's form for members
 * (done, next, blockers, confidence 1–5; due Tuesday 23:59 Dhaka), who still owes one, and the
 * feed grouped by week with on-time marks and blocker replies. Check-ins can't be edited once
 * posted (they are reputation evidence); corrections go in a reply. The client reads and replies.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { CalendarCheck, CircleAlert } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { ApiError } from "@/api/client";
import type { Checkin, CheckinFeed } from "@/api/types";
import { VIRTUALIZE_AFTER, VirtualList } from "@/components/VirtualList";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { Alert, EmptyState, ErrorState } from "@/components/ui/Feedback";
import { FormField, Textarea } from "@/components/ui/Field";
import { Slider } from "@/components/ui/Slider";
import { toast } from "@/components/ui/toast-store";
import { applyFieldErrors, messageFor } from "@/features/auth/errors";
import { formatDate, formatDateTime } from "@/lib/format";
import { byWeek, useCheckins, usePostCheckin } from "./checkinsApi";
import { useWorkspace } from "./context";

export const checkinSchema = z.object({
  done: z.string().trim().min(1, "Say what you finished").max(2000, "At most 2,000 characters"),
  next: z.string().trim().min(1, "Say what’s next").max(2000, "At most 2,000 characters"),
  blockers: z.string().trim().max(2000, "At most 2,000 characters"),
  confidence: z.number().int().min(1).max(5),
});
type CheckinForm = z.infer<typeof checkinSchema>;

const CONFIDENCE = ["", "Very unsure", "Unsure", "Fair", "Confident", "Very confident"];

export default function CheckinsTab() {
  const ws = useWorkspace();
  const q = useCheckins(ws.projectId);
  if (q.isPending) {
    return (
      <div className="space-y-4" aria-busy="true" aria-label="Loading check-ins">
        <Skeleton className="h-48 w-full rounded-xl" />
        <Skeleton className="h-32 w-full rounded-xl" />
      </div>
    );
  }
  if (q.isError) {
    return (
      <Card>
        <ErrorState
          title="Check-ins didn’t load"
          requestId={q.error instanceof ApiError ? q.error.requestId : null}
          onRetry={() => void q.refetch()}
        />
      </Card>
    );
  }
  const first = q.data.pages[0];
  const items = q.data.pages.flatMap((p) => p.items);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
      <div className="space-y-6">
        {ws.myUserId && first && !first.this_week.posted ? (
          <CheckinFormCard projectId={ws.projectId} week={first.this_week} />
        ) : null}
        {items.length === 0 ? (
          <Card>
            <EmptyState
              icon={<CalendarCheck />}
              title="No check-ins yet"
              description="Each member posts one a week: what they did, what’s next and what’s in the way."
            />
          </Card>
        ) : items.length > VIRTUALIZE_AFTER ? (
          // A long feed: week headings and check-ins as one list, drawn only on screen (D158).
          <VirtualList
            items={feedRows(items)}
            getKey={(r) => (r.kind === "week" ? `week-${r.week}` : r.c.id)}
            estimate={180}
            gap={12}
            aria-label="Check-ins"
            render={(r) =>
              r.kind === "week" ? (
                <h2 className="pt-2 text-body font-semibold">Week of {formatDate(r.week)}</h2>
              ) : (
                <CheckinCard checkin={r.c} />
              )
            }
          />
        ) : (
          byWeek(items).map((group) => (
            <section key={group.week} aria-labelledby={`week-${group.week}`} className="space-y-3">
              <h2 id={`week-${group.week}`} className="text-body font-semibold">
                Week of {formatDate(group.week)}
              </h2>
              <ul className="space-y-3">
                {group.items.map((c) => (
                  <li key={c.id}>
                    <CheckinCard checkin={c} />
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
        {q.hasNextPage ? (
          <Button
            variant="outline"
            loading={q.isFetchingNextPage}
            onClick={() => void q.fetchNextPage()}
          >
            Show earlier weeks
          </Button>
        ) : null}
      </div>
      {first ? <ThisWeekCard week={first.this_week} isMember={ws.myUserId !== null} /> : null}
    </div>
  );
}

function ThisWeekCard({ week, isMember }: { week: CheckinFeed["this_week"]; isMember: boolean }) {
  return (
    <Card>
      <CardHeader
        title="This week"
        description={`Due ${formatDateTime(week.due_at)} (Dhaka time).`}
      />
      <div className="space-y-3 px-5 pb-5 text-body-sm">
        {isMember && week.posted ? <Alert tone="success">You checked in this week.</Alert> : null}
        {week.missing.length === 0 ? (
          <p className="text-text-muted">Everyone has checked in.</p>
        ) : (
          <div>
            <p className="mb-1 font-medium text-text">Still to check in</p>
            <ul className="space-y-1">
              {week.missing.map((m) => (
                <li key={m.id} className="flex items-center gap-2 text-text-muted">
                  <CircleAlert className="size-4 text-warning" aria-hidden="true" />
                  {m.name}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}

type FeedRow = { kind: "week"; week: string } | { kind: "checkin"; c: Checkin };

function feedRows(items: Checkin[]): FeedRow[] {
  return byWeek(items).flatMap((g): FeedRow[] => [
    { kind: "week", week: g.week },
    ...g.items.map((c): FeedRow => ({ kind: "checkin", c })),
  ]);
}

function CheckinCard({ checkin }: { checkin: Checkin }) {
  return (
    <Card className="p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-medium text-text">{checkin.member.name}</span>
        {checkin.on_time ? (
          <Badge tone="success">On time</Badge>
        ) : (
          <Badge tone="warning">Late</Badge>
        )}
        <span className="text-caption text-text-muted">Confidence {checkin.confidence} of 5</span>
      </div>
      <dl className="space-y-2 text-body-sm">
        <div>
          <dt className="font-medium text-text">Done</dt>
          <dd className="whitespace-pre-wrap break-words text-text">{checkin.done}</dd>
        </div>
        <div>
          <dt className="font-medium text-text">Next</dt>
          <dd className="whitespace-pre-wrap break-words text-text">{checkin.next}</dd>
        </div>
        {checkin.blockers ? (
          <div className="rounded-md bg-warning-bg p-2">
            <dt className="font-medium text-text">Blockers</dt>
            <dd className="whitespace-pre-wrap break-words text-text">{checkin.blockers}</dd>
          </div>
        ) : null}
      </dl>
      {checkin.reply_count > 0 ? (
        <p className="mt-2 text-caption text-text-muted">
          {checkin.reply_count} {checkin.reply_count === 1 ? "reply" : "replies"}
        </p>
      ) : null}
    </Card>
  );
}

function CheckinFormCard({
  projectId,
  week,
}: {
  projectId: string;
  week: CheckinFeed["this_week"];
}) {
  const post = usePostCheckin(projectId);
  const [notice, setNotice] = useState<string | null>(null);
  const form = useForm<CheckinForm>({
    resolver: zodResolver(checkinSchema),
    defaultValues: { done: "", next: "", blockers: "", confidence: 3 },
  });
  const submit = form.handleSubmit(async (v) => {
    setNotice(null);
    try {
      await post.mutateAsync({ ...v, blockers: v.blockers || null });
      toast({ tone: "success", title: "Checked in" });
    } catch (e) {
      if (!applyFieldErrors(e, form.setError, ["done", "next", "blockers", "confidence"]))
        setNotice(messageFor(e));
    }
  });
  const errors = form.formState.errors;
  return (
    <Card>
      <CardHeader
        title="Your check-in"
        description={`For the week of ${formatDate(week.week_start)}. You can’t edit it after posting.`}
      />
      <form noValidate onSubmit={(e) => void submit(e)} className="space-y-4 px-5 pb-5">
        {notice ? <Alert tone="danger">{notice}</Alert> : null}
        <FormField label="What did you finish?" required error={errors.done?.message}>
          <Textarea rows={3} maxLength={2000} {...form.register("done")} />
        </FormField>
        <FormField label="What’s next?" required error={errors.next?.message}>
          <Textarea rows={3} maxLength={2000} {...form.register("next")} />
        </FormField>
        <FormField
          label="Anything in your way?"
          hint="The lead is told, and teammates can reply."
          error={errors.blockers?.message}
        >
          <Textarea rows={2} maxLength={2000} {...form.register("blockers")} />
        </FormField>
        <Controller
          control={form.control}
          name="confidence"
          render={({ field }) => (
            <Slider
              label="How confident are you about next week?"
              value={field.value}
              onChange={field.onChange}
              min={1}
              max={5}
              step={1}
              format={(v) => `${String(v)}: ${CONFIDENCE[v] ?? ""}`}
            />
          )}
        />
        <Button type="submit" loading={form.formState.isSubmitting}>
          Post check-in
        </Button>
      </form>
    </Card>
  );
}
