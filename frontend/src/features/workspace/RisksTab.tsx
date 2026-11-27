/**
 * Risks tab `/w/:projectId/risks` (spec §13.5 #39; §9.11; D151): every open risk grouped by
 * severity, each with one sentence of why and its suggested actions. The client also sees the
 * budget risks; members never do. Requesting a removal stays the client's choice (§9.9).
 */
import { ApiError } from "@/api/client";
import { RiskList, type ActionTarget } from "@/components/RiskList";
import { Card, Skeleton } from "@/components/ui/Display";
import { ErrorState } from "@/components/ui/Feedback";
import { formatDateTime } from "@/lib/format";
import { useWorkspace, type WorkspaceContext } from "./context";
import { ACTION_LABEL, useRisks } from "./monitoringApi";

/** Where each suggested action leads for this viewer (none they can't take). */
export function actionTarget(ws: WorkspaceContext): ActionTarget {
  const base = `/w/${ws.projectId}`;
  return (action: string) => {
    const label = ACTION_LABEL[action];
    if (!label) return null;
    switch (action) {
      case "REPLAN":
        return { to: `${base}/timeline`, label };
      case "MESSAGE_TEAM":
      case "MESSAGE_MEMBER":
        return { to: `${base}/discussion`, label };
      case "FIND_REPLACEMENT":
        return ws.isClient ? { to: `/client/projects/${ws.projectId}/team`, label } : null;
      case "REASSIGN":
        return ws.isLead ? { to: `${base}/tasks`, label } : null;
      default:
        return null;
    }
  };
}

export default function RisksTab() {
  const ws = useWorkspace();
  const q = useRisks(ws.projectId);
  if (q.isPending) {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Loading risks">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
      </div>
    );
  }
  if (q.isError) {
    return (
      <Card>
        <ErrorState
          title="Risks didn’t load"
          requestId={q.error instanceof ApiError ? q.error.requestId : null}
          onRetry={() => void q.refetch()}
        />
      </Card>
    );
  }
  return (
    <div className="space-y-4">
      {q.data.evaluated_at ? (
        <p className="text-caption text-text-muted" data-volatile>
          Checked {formatDateTime(q.data.evaluated_at)}. Risks update after each change.
        </p>
      ) : null}
      <RiskList risks={q.data.items} target={actionTarget(ws)} />
    </div>
  );
}
