/** What every workspace tab knows about the caller (D142), read from the layout's outlet. */
import { useOutletContext } from "react-router";
import type { TeamView } from "@/api/types";

export interface WorkspaceTab {
  path: string;
  label: string;
  /** Filled by a later phase: shown, not linked, saying which. */
  later?: string;
}

/** §13.4's order (D160). */
export const WORKSPACE_TABS: WorkspaceTab[] = [
  { path: "overview", label: "Overview" },
  { path: "tasks", label: "Tasks" },
  { path: "timeline", label: "Timeline" },
  { path: "milestones", label: "Milestones" },
  { path: "team", label: "Team" },
  { path: "check-ins", label: "Check-ins" },
  { path: "files", label: "Files" },
  { path: "discussion", label: "Discussion" },
  { path: "payments", label: "Payments", later: "Phase 10" },
  { path: "evidence", label: "Evidence" },
  { path: "risks", label: "Risks" },
];

export interface WorkspaceContext {
  team: TeamView;
  projectId: string;
  /** The project's client: reads everything, comments, posts and uploads only (§1.6). */
  isClient: boolean;
  /** The caller's user id when they are a member (the lead included). */
  myUserId: string | null;
  isLead: boolean;
  /** Past TEAM_PENDING: the work tabs are open. */
  started: boolean;
}

export function workspaceContext(team: TeamView): WorkspaceContext {
  const member = team.view === "member" ? team : null;
  const me = member?.members.find((m) => m.id === member.my_member_id);
  return {
    team,
    projectId: team.project_id,
    isClient: team.view === "client",
    myUserId: me?.developer_id ?? null,
    isLead: Boolean(me?.is_lead && me.status === "ACTIVE"),
    started: team.project_status !== "TEAM_PENDING",
  };
}

export function useWorkspace(): WorkspaceContext {
  return useOutletContext<WorkspaceContext>();
}
