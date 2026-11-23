/**
 * Developer dashboard invitations and teams (spec §13.5 #9; D120, D123, D124).
 *
 * - A banner per pending invitation: project, role, your price and days, a live countdown, Accept
 *   and Decline (a dialog with an optional reason). A refused accept (409 `UNAVAILABLE`) shows
 *   the server's sentence about free hours inline and leaves the invitation open.
 * - Answered invitations of the last 30 days show their outcome once.
 * - A card per team you are in: "You are team lead" with "Decline the lead role", and for a
 *   started project a link into the workspace (`/w/:projectId/team`).
 */
import { Crown, PartyPopper, Users } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import type { MyInvitation, MyMembership } from "@/api/types";
import { ExpiryCountdown } from "@/components/ExpiryCountdown";
import { ReasonDialog } from "@/components/ReasonDialog";
import { Button } from "@/components/ui/Button";
import { Badge, Card } from "@/components/ui/Display";
import { Alert } from "@/components/ui/Feedback";
import { ConfirmDialog } from "@/components/ui/Overlay";
import { toast } from "@/components/ui/toast-store";
import { formatDays, formatMoney } from "@/lib/format";
import { useAnswerInvitation, useDeclineLead, useMyInvitations } from "./api";

export function InvitationBanners() {
  const q = useMyInvitations();
  if (!q.data) return null;
  const pending = q.data.invitations.filter((i) => i.state === "PENDING");
  const answered = q.data.invitations.filter((i) => i.state !== "PENDING").slice(0, 3);
  const teams = q.data.memberships;
  if (pending.length + answered.length + teams.length === 0) return null;
  return (
    <section aria-label="Your invitations and teams" className="mb-6 flex flex-col gap-4">
      {pending.map((inv) => (
        <InvitationBanner key={inv.id} invitation={inv} />
      ))}
      {teams.map((m) => (
        <TeamCard key={m.member_id} membership={m} />
      ))}
      {answered
        .filter((i) => !teams.some((t) => t.project_id === i.project_id))
        .map((i) => (
          <p key={i.id} className="text-body-sm text-text-muted">
            {outcome(i)}
          </p>
        ))}
    </section>
  );
}

function outcome(i: MyInvitation): string {
  if (i.state === "ACCEPTED") return `You joined the team for “${i.project_title}”.`;
  if (i.state === "DECLINED") return `You declined the invitation for “${i.project_title}”.`;
  if (i.state === "EXPIRED") return `The invitation for “${i.project_title}” expired.`;
  return `The invitation for “${i.project_title}” is closed.`;
}

function InvitationBanner({ invitation: inv }: { invitation: MyInvitation }) {
  const answer = useAnswerInvitation(inv.project_id);
  const [error, setError] = useState<string | null>(null);
  return (
    <Card className="border-primary/40 p-5">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-body font-semibold text-text">
            <PartyPopper className="size-5 text-primary" aria-hidden="true" />
            {inv.is_replacement ? "You were selected as a replacement" : "You were selected"}
          </p>
          <p className="mt-1 text-body-sm text-text">
            {inv.slot_label} on “{inv.project_title}”, for {formatMoney(inv.price_paisa)} in{" "}
            {formatDays(inv.days_needed)}.
          </p>
          {inv.expires_at ? <ExpiryCountdown expiresAt={inv.expires_at} className="mt-2" /> : null}
        </div>
        <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
          <ReasonDialog
            trigger={<Button variant="outline">Decline</Button>}
            title="Decline this invitation?"
            description="The client is told and DevSync looks for someone else. You can add a reason for the client."
            label="Reason (optional)"
            actionLabel="Decline invitation"
            optional
            destructive
            onSubmit={(reason) =>
              answer
                .mutateAsync({ id: inv.id, accept: false, reason: reason || undefined })
                .then(() => {
                  toast({ tone: "success", title: "Invitation declined" });
                })
            }
          />
          <Button
            loading={answer.isPending && answer.variables.accept}
            onClick={() => {
              setError(null);
              answer.mutate(
                { id: inv.id, accept: true },
                {
                  onSuccess: () => {
                    toast({ tone: "success", title: "You joined the team" });
                  },
                  onError: (e) => {
                    setError(e instanceof ApiError ? e.message : "That didn’t work. Try again.");
                  },
                },
              );
            }}
          >
            Accept
          </Button>
        </div>
      </div>
      {error ? (
        <Alert tone="warning" title="You can’t accept yet" className="mt-4">
          {error}
        </Alert>
      ) : null}
    </Card>
  );
}

function TeamCard({ membership: m }: { membership: MyMembership }) {
  const declineLead = useDeclineLead(m.project_id);
  const started = m.project_status === "IN_PROGRESS";
  return (
    <Card className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2 text-body font-semibold text-text">
          <Users className="size-5 text-text-muted" aria-hidden="true" />
          {m.project_title}
          {m.is_lead ? (
            <Badge tone="info" icon={false}>
              <Crown className="size-3.5" aria-hidden="true" /> You are team lead
            </Badge>
          ) : null}
        </p>
        <p className="mt-1 text-body-sm text-text-muted">
          {started
            ? "The project has started. The team workspace is open."
            : m.status === "ACTIVE"
              ? "You joined. The project starts when every place is filled and a lead is chosen."
              : "Waiting for your answer."}
        </p>
      </div>
      <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
        {m.is_lead ? (
          <ConfirmDialog
            trigger={<Button variant="outline">Decline the lead role</Button>}
            title="Decline the lead role?"
            description="You stay in the team; the client chooses another lead."
            confirmLabel="Decline the lead role"
            onConfirm={async () => {
              await declineLead.mutateAsync(undefined);
              toast({ tone: "success", title: "You are no longer the team lead" });
            }}
          />
        ) : null}
        {started ? (
          <Button asChild>
            <Link to={`/w/${m.project_id}/team`}>Open workspace</Link>
          </Button>
        ) : null}
      </div>
    </Card>
  );
}
