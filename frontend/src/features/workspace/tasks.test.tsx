/** Tasks tab (screen 30; D143, D158, §13.7): the board from the API, the client's read-only
 * board, the lead's New task, an optimistic move that the server confirms, and one it refuses
 * (rolled back, with the server's reason); the board's own refusal rule. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { TaskCard } from "@/api/types";
import { Toaster } from "@/components/ui/Toaster";
import { renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import TasksTab, { boardRefusal, dhakaToday } from "./TasksTab";
import WorkspaceLayout from "./WorkspaceLayout";

const API = "https://testserver/api/v1";
const PID = "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c";
const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });

const member = (over: Record<string, unknown> = {}) => ({
  id: "m1", developer_id: "lead", developer_name: "Arif Hossain", slot_id: "s1",
  slot_label: "React developer", status: "ACTIVE", is_lead: true, is_newcomer: false,
  competency: 0.74, teamwork: 0.66, hours_per_week: 20, joined_at: null, invitation: null,
  is_you: false, ...over,
}); // prettier-ignore
const team = (view: "member" | "client", me = "m2") => ({
  project_id: PID, project_title: "Inventory dashboard", project_status: "IN_PROGRESS",
  project_version: 6, team_id: "t", team_status: "ACTIVE", lead_member_id: "m1", view,
  members: [member(), member({ id: "m2", developer_id: "dev", developer_name: "Nusrat Jahan",
                               is_lead: false, is_you: me === "m2" })],
  my_member_id: me, lead_change_requests: [],
  ...(view === "client" ? { recommendation: null, can_choose_lead: false, can_start: false,
                            start_blockers: [], removal_requests: [], repair: null } : {}),
}); // prettier-ignore
const card = (id: string, over: Partial<TaskCard> = {}): TaskCard => ({
  id, milestone_id: "ms1", title: `Task ${id}`, status: "TODO",
  assignee: { id: "dev", name: "Nusrat Jahan" }, deadline: null, estimate_hours: "8.0",
  difficulty: "MEDIUM", position: "V", progress_pct: 0, blocked_by: 0, evidence_count: 0,
  comment_count: 0, last_activity_at: "2026-11-20T05:00:00Z", version: 1, ...over,
}); // prettier-ignore
// CPM "duration" lives in a named constant: the motion-lint rule forbids numeric `duration:`
// literals (they look like animation timings), as in projects.test.tsx.
const PLAN_DAYS = 8;
const plan = {
  baseline_version: 1, duration: PLAN_DAYS, edges: [], critical_paths: [], deadline_days: 30,
  exceeds_deadline: false,
  nodes: [{ key: "ms1", name: "Build", es: 0, ef: 8, ls: 0, lf: 8, slack: 0, critical: true }],
}; // prettier-ignore

function board(cards: TaskCard[]) {
  return http.get(`${API}/projects/${PID}/tasks`, ({ request }) => {
    const status = new URL(request.url).searchParams.get("status");
    return HttpResponse.json({ items: cards.filter((c) => c.status === status), next_cursor: null });
  });
}

function show(view: "member" | "client", cards: TaskCard[], me = "m2") {
  server.use(
    csrf(),
    http.get(`${API}/projects/${PID}/team`, () => HttpResponse.json(team(view, me))),
    http.get(`${API}/projects/${PID}/plan`, () => HttpResponse.json(plan)),
    board(cards),
  );
  return renderRoutes(
    [
      {
        path: "/w/:projectId",
        element: (
          <>
            <WorkspaceLayout />
            <Toaster />
          </>
        ),
        children: [{ path: "tasks", element: <TasksTab /> }],
      },
    ],
    `/w/${PID}/tasks`,
  );
}

describe("TasksTab", () => {
  it("shows the board to a member, with handles on their own tasks only", async () => {
    show("member", [card("a"), card("b", { assignee: { id: "lead", name: "Arif Hossain" } })]);
    expect(await screen.findByRole("button", { name: "Move Task a" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Move Task b" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New task" })).not.toBeInTheDocument();
  });

  it("gives the client a read-only board (§1.6)", async () => {
    show("client", [card("a")]);
    expect(await screen.findByRole("button", { name: "Task a" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Move Task/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /another column/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Only mine")).not.toBeInTheDocument();
  });

  it("gives the lead New task", async () => {
    show("member", [card("a")], "m1");
    expect((await screen.findAllByRole("button", { name: "New task" })).length).toBeGreaterThan(0);
  });

  it("explains an empty board", async () => {
    show("member", []);
    expect(await screen.findByText("No tasks yet")).toBeInTheDocument();
  });

  it("moves a task at once and keeps it when the server agrees", async () => {
    let sent: unknown = null;
    let ifMatch: string | null = null;
    const moved = card("a", { status: "IN_PROGRESS", progress_pct: 50, version: 2 });
    show("member", [card("a")]);
    server.use(
      http.post(`${API}/tasks/a/move`, async ({ request }) => {
        sent = await request.json();
        ifMatch = request.headers.get("If-Match");
        return HttpResponse.json(moved);
      }),
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Move Task a to another column" }));
    server.use(board([moved]));
    await user.click(await screen.findByRole("menuitem", { name: "Move to In progress" }));
    const doing = screen.getByRole("region", { name: /In progress/ });
    expect(await within(doing).findByRole("button", { name: "Task a" })).toBeInTheDocument();
    expect(sent).toEqual({ status: "IN_PROGRESS", after_id: null, before_id: null });
    expect(ifMatch).toBe("1");
  });

  it("puts a refused move back and says why", async () => {
    show("member", [card("a")]);
    server.use(
      http.post(`${API}/tasks/a/move`, () =>
        HttpResponse.json(
          {
            error: {
              code: "MILESTONE_NOT_ACTIVE",
              message: "Work on this milestone can start once it's active.",
              request_id: "r",
            },
          },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Move Task a to another column" }));
    await user.click(await screen.findByRole("menuitem", { name: "Move to In progress" }));
    expect(await screen.findByText("That move didn’t happen")).toBeInTheDocument();
    const todo = screen.getByRole("region", { name: /To do/ });
    expect(await within(todo).findByRole("button", { name: "Task a" })).toBeInTheDocument();
  });

  it("refuses a skipped column or open dependencies before asking the server", () => {
    expect(boardRefusal(card("a"), "REVIEW")).toBe("Move it to In progress first.");
    expect(boardRefusal(card("a", { status: "DONE" }), "IN_PROGRESS")).toBe(
      "Move it to Review first.",
    );
    expect(boardRefusal(card("a", { status: "REVIEW", blocked_by: 2 }), "DONE")).toBe(
      "Finish the tasks it waits for first.",
    );
    expect(boardRefusal(card("a"), "IN_PROGRESS")).toBeNull();
  });

  it("knows today's date in Dhaka", () => {
    expect(dhakaToday(new Date("2026-11-27T19:30:00Z"))).toBe("2026-11-28"); // 01:30 in Dhaka
  });
});
