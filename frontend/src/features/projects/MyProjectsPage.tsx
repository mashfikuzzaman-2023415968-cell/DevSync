/**
 * The client's projects (spec §13.5 client "My projects"). A list with status, budget, team
 * size and deadline; each row links to its plan. Draft and bidding projects can be cancelled,
 * which asks for a short reason.
 */
import { CirclePlus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import type { ProjectListItem } from "@/api/types";
import { ApiError } from "@/api/client";
import { NodeArt } from "@/components/brand/NodeArt";
import { Button } from "@/components/ui/Button";
import { Badge, Card, Skeleton, type Tone } from "@/components/ui/Display";
import { Dialog } from "@/components/ui/Overlay";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { FormField, Textarea } from "@/components/ui/Field";
import { toast } from "@/components/ui/toast-store";
import { formatDate, formatDays, formatMoney } from "@/lib/format";
import { useCancelProject, useMyProjects } from "./api";

const STATUS_TONE: Record<string, Tone> = {
  DRAFT: "neutral",
  BIDDING: "info",
  FORMING: "info",
  TEAM_PENDING: "warning",
  IN_PROGRESS: "primary",
  ON_HOLD: "warning",
  REVIEW_WINDOW: "warning",
  COMPLETED: "success",
  CANCELLED: "danger",
};

const CANCELLABLE = new Set(["DRAFT", "BIDDING", "FORMING", "TEAM_PENDING"]);

function label(status: string): string {
  return status.charAt(0) + status.slice(1).toLowerCase().replace(/_/g, " ");
}

export default function MyProjectsPage() {
  const projects = useMyProjects();

  const action = (
    <Button asChild>
      <Link to="/client/projects/new">
        <CirclePlus aria-hidden="true" />
        Create project
      </Link>
    </Button>
  );

  return (
    <>
      <PageHeader
        title="My projects"
        description="Everything you've planned, open for bids or in progress."
        action={action}
      />

      {projects.isLoading ? (
        <Card>
          <Skeleton className="h-40 w-full" />
        </Card>
      ) : projects.isError ? (
        <Card>
          <ErrorState
            requestId={projects.error instanceof ApiError ? projects.error.requestId : null}
            onRetry={() => void projects.refetch()}
          />
        </Card>
      ) : (projects.data ?? []).length === 0 ? (
        <Card>
          <EmptyState
            art={<NodeArt />}
            title="No projects yet"
            description="Describe the work, split it into milestones and DevSync shows the critical path before anyone bids."
            action={action}
          />
        </Card>
      ) : (
        <Card className="overflow-hidden p-0">
          <ul className="divide-y divide-border">
            {(projects.data ?? []).map((p) => (
              <ProjectRow key={p.id} project={p} />
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

function ProjectRow({ project: p }: { project: ProjectListItem }) {
  return (
    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Link
            to={`/client/projects/${p.id}/plan`}
            className="truncate font-medium text-text hover:text-primary hover:underline"
          >
            {p.title}
          </Link>
          <Badge tone={STATUS_TONE[p.status] ?? "neutral"}>{label(p.status)}</Badge>
        </div>
        <p className="mt-1 text-body-sm text-text-muted">
          {formatMoney(p.budget_paisa)} · {p.team_size} people · {formatDays(p.deadline_days)}
          {p.bidding_deadline ? ` · bids close ${formatDate(p.bidding_deadline)}` : ""}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button asChild variant="outline" size="sm">
          <Link to={`/client/projects/${p.id}/plan`}>View plan</Link>
        </Button>
        {CANCELLABLE.has(p.status) && <CancelDialog id={p.id} title={p.title} />}
      </div>
    </li>
  );
}

function CancelDialog({ id, title }: { id: string; title: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const cancel = useCancelProject(id);
  const ready = reason.trim().length >= 3;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setReason("");
      }}
      trigger={
        <Button variant="ghost" size="sm">
          Cancel
        </Button>
      }
      title="Cancel this project?"
      description={`“${title}” will be withdrawn. Tell bidders why.`}
      footer={
        <>
          <Button
            variant="outline"
            onClick={() => {
              setOpen(false);
            }}
          >
            Keep it
          </Button>
          <Button
            variant="destructive"
            loading={cancel.isPending}
            disabled={!ready}
            onClick={() => {
              cancel.mutate(
                { reason: reason.trim() },
                {
                  onSuccess: () => {
                    toast({ tone: "success", title: "Project cancelled" });
                    setOpen(false);
                  },
                  onError: (e) => {
                    toast({
                      tone: "danger",
                      title: "Could not cancel",
                      description: e instanceof ApiError ? e.message : "Please try again.",
                    });
                  },
                },
              );
            }}
          >
            Cancel project
          </Button>
        </>
      }
    >
      <FormField label="Reason" hint="Shared with anyone who bid.">
        {(a11y) => (
          <Textarea
            {...a11y}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
            }}
            rows={3}
            maxLength={500}
            placeholder="e.g. Requirements changed and we're re-scoping."
          />
        )}
      </FormField>
    </Dialog>
  );
}
