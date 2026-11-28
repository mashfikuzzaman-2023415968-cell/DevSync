/** Overview, Risks, Timeline and Milestones tabs (screens 29, 31, 32, 39; D151, D152): the
 * client's overview with the budget donut and a member's without it, the forecast sentence, risks
 * grouped by severity with actions only the viewer can take, the baseline vs forecast schedule
 * and the read-only milestones; plus the donut's table view. */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import type { Dashboard, RiskItem } from "@/api/types";
import { BudgetDonut } from "@/components/BudgetDonut";
import { RiskList } from "@/components/RiskList";
import { renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import MilestonesTab from "./MilestonesTab";
import OverviewTab, { forecastSentence } from "./OverviewTab";
import RisksTab from "./RisksTab";
import TimelineTab from "./TimelineTab";
import WorkspaceLayout from "./WorkspaceLayout";

const API = "https://testserver/api/v1";
const PID = "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c";
const PLAN_DAYS = 23; // a named constant: the motion lint forbids numeric `duration:` literals

const member = {
  id: "m2", developer_id: "dev", developer_name: "Nusrat Jahan", slot_id: "s1",
  slot_label: "React developer", status: "ACTIVE", is_lead: false, is_newcomer: false,
  competency: 0.7, teamwork: 0.6, hours_per_week: 20, joined_at: null, invitation: null,
  is_you: true,
}; // prettier-ignore
const team = (view: "member" | "client") => ({
  project_id: PID, project_title: "Inventory dashboard", project_status: "IN_PROGRESS",
  project_version: 3, team_id: "t", team_status: "ACTIVE", lead_member_id: "m1", view,
  members: [member], my_member_id: "m2", lead_change_requests: [],
  ...(view === "client" ? { recommendation: null, can_choose_lead: false, can_start: false,
                            start_blockers: [], removal_requests: [], repair: null } : {}),
}); // prettier-ignore
const risk = (over: Partial<RiskItem> = {}): RiskItem => ({
  id: "r1", type: "CRITICAL_PATH_DELAY", severity: "CRITICAL", entity_type: "MILESTONE",
  entity_id: "ms", title: "Dashboard frontend late pushes the deadline by 2 days",
  why: "It is on the critical path.", actions: ["REPLAN", "MESSAGE_TEAM"],
  opened_at: "2026-11-23T06:00:00Z", ...over,
}); // prettier-ignore
const dashboard = (view: "member" | "client"): Dashboard => ({
  view, progress_pct: 49, schedule: { actual_pct: 49, planned_pct: 45 },
  forecast: { finish_day: 25, finish_date: "2026-12-08", baseline_days: 23, impact_days: 2 },
  health: "AT_RISK", overall_risk: "CRITICAL", top_risks: [risk()],
  next_milestone: { id: "ms", name: "Inventory API", status: "ACTIVE", progress_pct: 70,
                    planned_finish_date: "2026-11-23", forecast_finish_date: "2026-11-29" },
  tasks: { todo: 9, in_progress: 0, review: 0, done: 11 }, evaluated_at: "2026-11-27T06:00:00Z",
  ...(view === "client" ? { budget: { budget_paisa: 12_000_000, released_paisa: 0,
                                      committed_paisa: 0, remaining_paisa: 12_000_000 } } : {}),
}) as Dashboard; // prettier-ignore
const plan = {
  baseline_version: 1, duration: PLAN_DAYS, deadline_days: 30, exceeds_deadline: false,
  edges: [{ predecessor: "a", successor: "b" }], critical_paths: [["A", "B"]],
  nodes: [
    { key: "a", name: "Inventory API", es: 3, ef: 10, ls: 9, lf: 16, slack: 6, critical: false, share_bp: 2000 },
    { key: "b", name: "Dashboard frontend", es: 8, ef: 16, ls: 8, lf: 16, slack: 0, critical: true, share_bp: 2500 },
  ],
  forecast: {
    today: 12, finish_day: 25, impact_days: 2, start_date: "2026-11-15", evaluated_at: null,
    nodes: [
      { key: "a", status: "ACTIVE", progress_pct: 70, forecast_es: 4, forecast_ef: 16, days_late: 6,
        revision_count: 0, actual_start: "2026-11-19", actual_finish: null },
      { key: "b", status: "ACTIVE", progress_pct: 40, forecast_es: 8, forecast_ef: 18, days_late: 2,
        revision_count: 1, actual_start: "2026-11-23", actual_finish: null },
    ],
  },
}; // prettier-ignore

function show(view: "member" | "client", path: string, element: React.ReactNode) {
  server.use(
    http.get(`${API}/projects/${PID}/team`, () => HttpResponse.json(team(view))),
    http.get(`${API}/projects/${PID}/dashboard`, () => HttpResponse.json(dashboard(view))),
    http.get(
      `${API}/projects/${PID}/risks`,
      () =>
      HttpResponse.json({ items: [risk(), risk({ id: "r2", type: "INACTIVE_MEMBER",
        severity: "MEDIUM", title: "Rafi has been inactive for 10 days",
        actions: ["MESSAGE_MEMBER", "FIND_REPLACEMENT"] })], evaluated_at: null }), // prettier-ignore
    ),
    http.get(
      `${API}/projects/${PID}/activity`,
      () =>
      HttpResponse.json({ items: [{ id: "e1", type: "task.done", actor: null, subject: null,
        summary: "Nusrat Jahan finished a task", entity_type: "TASK", entity_id: null,
        at: "2026-11-27T05:00:00Z" }], next_cursor: null }), // prettier-ignore
    ),
    http.get(`${API}/projects/${PID}/plan`, () => HttpResponse.json(plan)),
  );
  renderRoutes(
    [{ path: "/w/:projectId", element: <WorkspaceLayout />, children: [{ path, element }] }],
    `/w/${PID}/${path}`,
  );
}

describe("OverviewTab", () => {
  it("shows the client progress, forecast, health, top risks and the budget", async () => {
    show("client", "overview", <OverviewTab />);
    expect(await screen.findByText("Dashboard frontend late pushes the deadline by 2 days"))
      .toBeInTheDocument(); // prettier-ignore
    expect(screen.getByText("At risk")).toBeInTheDocument();
    expect(screen.getByText("+2 days")).toBeInTheDocument();
    expect(screen.getByText(/49% done; 45% was planned by today/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Budget" })).toBeInTheDocument();
    expect(screen.getByText("Nusrat Jahan finished a task")).toBeInTheDocument();
  });

  it("gives members no budget", async () => {
    show("member", "overview", <OverviewTab />);
    expect(await screen.findByText("At risk")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Budget" })).not.toBeInTheDocument();
    expect(screen.queryByText(/৳/)).not.toBeInTheDocument();
  });

  it("says when the work is forecast to end", () => {
    expect(forecastSentence(dashboard("member"))).toBe(
      "Forecast to finish on 8 Dec 2026, 2 days after the plan.",
    );
  });
});

describe("RisksTab", () => {
  it("groups risks and offers only the client the replacement action", async () => {
    show("client", "risks", <RisksTab />);
    expect(await screen.findByRole("heading", { name: /Critical/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Medium/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request removal or a replacement" })).toHaveAttribute(
      "href",
      `/client/projects/${PID}/team`,
    );
    expect(screen.getAllByRole("link", { name: "Re-plan on the Timeline" })[0]).toHaveAttribute(
      "href",
      `/w/${PID}/timeline`,
    );
  });

  it("hides actions a member can't take", async () => {
    show("member", "risks", <RisksTab />);
    expect(await screen.findByRole("heading", { name: /Critical/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Request removal or a replacement" }))
      .not.toBeInTheDocument(); // prettier-ignore
  });
});

describe("TimelineTab and MilestonesTab", () => {
  it("explains the forecast against the plan", async () => {
    show("member", "timeline", <TimelineTab />);
    expect(await screen.findByText(/ends on day 25, 2 days after the 23-day plan/))
      .toBeInTheDocument(); // prettier-ignore
  });

  it("lists milestones read-only with progress, forecast and revisions", async () => {
    show("client", "milestones", <MilestonesTab />);
    expect(await screen.findByRole("heading", { name: "Dashboard frontend" })).toBeInTheDocument();
    expect(screen.getByText(/1 revision\./)).toBeInTheDocument();
    expect(screen.getByText(/2 days late/)).toBeInTheDocument();
    expect(screen.getByText("Submitting, reviewing and paying for milestones arrive in Phase 10."))
      .toBeInTheDocument(); // prettier-ignore
    expect(screen.queryByRole("button", { name: /submit/i })).not.toBeInTheDocument();
  });
});

describe("BudgetDonut and RiskList", () => {
  it("has a table view and says nothing is funded yet", async () => {
    render(
      <BudgetDonut budget={{ budget_paisa: 12_000_000, released_paisa: 0, committed_paisa: 0,
                             remaining_paisa: 12_000_000 }} />, // prettier-ignore
    );
    expect(screen.getByText(/Nothing is funded or released yet/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("radio", { name: "View as table" }));
    const table = screen.getByRole("table");
    expect(within(table).getByRole("rowheader", { name: "Remaining" })).toBeInTheDocument();
  });

  it("explains an empty list", () => {
    render(
      <MemoryRouter>
        <RiskList risks={[]} target={() => null} />
      </MemoryRouter>,
    );
    expect(screen.getByText("No open risks")).toBeInTheDocument();
  });
});
