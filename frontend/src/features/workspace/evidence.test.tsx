/** Evidence tab, My projects and the long-list virtualization (item 11; D144, D156, D158):
 * per-member facts with a departed member marked, the activity feed with "Show earlier
 * activity", the error state; the developer's My projects with Active/Completed in the address
 * and the empty state; the client's project pulse; `VirtualList` draws every row up to 50 and
 * only part of a longer list. */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { ActivityItem, MemberEvidence, MyProject } from "@/api/types";
import { VIRTUALIZE_AFTER, VirtualList } from "@/components/VirtualList";
import DevProjectsPage from "@/features/projects/DevProjectsPage";
import { ClientProjectPulse } from "@/features/projects/ProjectPulse";
import { renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import EvidenceTab from "./EvidenceTab";
import WorkspaceLayout from "./WorkspaceLayout";

const API = "https://testserver/api/v1";
const PID = "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c";
const team = {
  project_id: PID, project_title: "Inventory dashboard", project_status: "IN_PROGRESS",
  project_version: 3, team_id: "t", team_status: "ACTIVE", lead_member_id: "m1", view: "member",
  members: [], my_member_id: "m2", lead_change_requests: [],
}; // prettier-ignore
const member = (name: string, over: Partial<MemberEvidence> = {}): MemberEvidence => ({
  member: { id: name, name }, slot_label: "React developer", status: "ACTIVE",
  checkins_on_time: 2, checkins_expected: 3, tasks_done: 4, hours_done: "8.0", comments: 5,
  replies: 1, blockers_answered: 1, last_active_at: "2026-12-10T05:00:00Z", ...over,
}); // prettier-ignore
const event = (id: string, summary: string): ActivityItem => ({
  id, type: "task.done", actor: null, subject: null, summary, entity_type: "TASK",
  entity_id: null, at: "2026-12-10T05:00:00Z",
}); // prettier-ignore

function showEvidence(members: MemberEvidence[], pages: ActivityItem[][]) {
  server.use(
    http.get(`${API}/projects/${PID}/team`, () => HttpResponse.json(team)),
    http.get(`${API}/projects/${PID}/evidence`, () => HttpResponse.json({ members })),
    http.get(`${API}/projects/${PID}/activity`, ({ request }) => {
      const cursor = new URL(request.url).searchParams.get("cursor");
      const page = cursor ? Number(cursor) : 0;
      return HttpResponse.json({
        items: pages[page] ?? [],
        next_cursor: page + 1 < pages.length ? String(page + 1) : null,
      });
    }),
  );
  renderRoutes(
    [
      {
        path: "/w/:projectId",
        element: <WorkspaceLayout />,
        children: [{ path: "evidence", element: <EvidenceTab /> }],
      },
    ],
    `/w/${PID}/evidence`,
  );
}

describe("EvidenceTab", () => {
  it("shows what each member did, marking members who left", async () => {
    showEvidence(
      [member("Nusrat Jahan"), member("Imran Hossain", { status: "LEFT", last_active_at: null })],
      [[event("e1", "Nusrat finished “Stock table”")]],
    );
    const nusrat = (await screen.findByText("Nusrat Jahan")).closest("li");
    if (!nusrat) throw new Error("no row");
    expect(within(nusrat).getByText("2 of 3")).toBeInTheDocument();
    expect(within(nusrat).getByText("4 (8.0 h estimated)")).toBeInTheDocument();
    const imran = screen.getByText("Imran Hossain").closest("li");
    if (!imran) throw new Error("no row");
    expect(within(imran).getByText("Left")).toBeInTheDocument();
    expect(within(imran).getByText("No activity yet")).toBeInTheDocument();
    expect(screen.getByText("Nusrat finished “Stock table”")).toBeInTheDocument();
  });

  it("loads earlier activity on request", async () => {
    showEvidence([member("Nusrat Jahan")], [[event("e2", "Second")], [event("e1", "First")]]);
    expect(await screen.findByText("Second")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Show earlier activity" }));
    expect(await screen.findByText("First")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show earlier activity" })).not.toBeInTheDocument();
  });

  it("explains a failed load", async () => {
    showEvidence([], [[]]);
    server.use(
      http.get(`${API}/projects/${PID}/evidence`, () =>
        HttpResponse.json({ error: { code: "INTERNAL_ERROR", message: "x" } }, { status: 500 }),
      ),
    );
    expect(await screen.findByText("The evidence didn’t load")).toBeInTheDocument();
  });
});

const mine = (id: string, over: Partial<MyProject> = {}): MyProject => ({
  project_id: id, title: `Project ${id}`, status: "IN_PROGRESS", role: "React developer",
  is_lead: false, progress_pct: 40, next_deadline: "2026-12-03", next_milestone: "Build",
  overall_risk: null, health: "HEALTHY", ...over,
}); // prettier-ignore

describe("DevProjectsPage", () => {
  it("lists active projects and switches to completed through the address", async () => {
    const seen: string[] = [];
    server.use(
      http.get(`${API}/me/projects`, ({ request }) => {
        const state = new URL(request.url).searchParams.get("state") ?? "";
        seen.push(state);
        const items =
          state === "completed"
            ? [mine("done", { status: "COMPLETED", progress_pct: 100 })]
            : [mine("a")];
        return HttpResponse.json({ items, next_cursor: null });
      }),
    );
    const { router } = renderRoutes(
      [{ path: "/dev/projects", element: <DevProjectsPage /> }],
      "/dev/projects",
    );
    expect(await screen.findByRole("link", { name: "Project a" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("radio", { name: "Completed" }));
    expect(await screen.findByRole("link", { name: "Project done" })).toBeInTheDocument();
    expect(router.state.location.search).toBe("?state=completed");
    expect(seen).toEqual(["active", "completed"]);
  });

  it("says when there are no projects yet", async () => {
    server.use(
      http.get(`${API}/me/projects`, () => HttpResponse.json({ items: [], next_cursor: null })),
    );
    renderRoutes([{ path: "/dev/projects", element: <DevProjectsPage /> }], "/dev/projects");
    expect(await screen.findByText("No active projects yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse open projects" })).toHaveAttribute(
      "href",
      "/dev/find",
    );
  });
});

describe("ClientProjectPulse", () => {
  it("shows progress, days late and the risk in words", async () => {
    server.use(
      http.get(
        `${API}/projects/p1/dashboard`,
        () =>
        HttpResponse.json({
          view: "client", progress_pct: 49, schedule: { actual_pct: 49, planned_pct: 45 },
          forecast: { finish_day: 25, finish_date: "2026-12-08", baseline_days: 23, impact_days: 2 },
          health: "AT_RISK", overall_risk: "CRITICAL", top_risks: [], next_milestone: null,
          tasks: { todo: 1, in_progress: 1, review: 0, done: 2 }, evaluated_at: null,
          budget: { released_paisa: 0, committed_paisa: 0, remaining_paisa: 0 },
        }), // prettier-ignore
      ),
    );
    renderRoutes([{ path: "/", element: <ClientProjectPulse projectId="p1" /> }], "/");
    expect(await screen.findByText("49% done")).toBeInTheDocument();
    expect(screen.getByText("2 days late")).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.queryByText(/৳/)).not.toBeInTheDocument();
  });
});

describe("VirtualList", () => {
  const list = (n: number) => Array.from({ length: n }, (_, i) => `item ${String(i)}`);
  const draw = (items: string[]) =>
    render(
      <VirtualList
        items={items}
        getKey={(s) => s}
        estimate={40}
        render={(s) => <span>{s}</span>}
      />,
    );

  it("draws every row up to the threshold", () => {
    draw(list(VIRTUALIZE_AFTER));
    expect(screen.getAllByRole("listitem")).toHaveLength(VIRTUALIZE_AFTER);
  });

  it("draws only part of a longer list", () => {
    draw(list(500));
    const rows = screen.getAllByRole("listitem");
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(500);
    // jsdom has no layout, so which rows show isn't the browser's (the E2E checks scrolling);
    // that it draws a window, not all 500, is what this proves.
    expect(screen.getByRole("list")).toHaveAttribute("data-virtual");
  });
});
