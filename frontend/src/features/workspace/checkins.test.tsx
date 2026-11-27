/** Check-ins tab (screen 34; D145): the weekly form for a member who hasn't posted, its bounds,
 * posting, the feed grouped by week with on-time marks, who still owes one, and the client's
 * read-only view. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { Checkin } from "@/api/types";
import { Toaster } from "@/components/ui/Toaster";
import { renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import { byWeek } from "./checkinsApi";
import CheckinsTab, { checkinSchema } from "./CheckinsTab";
import WorkspaceLayout from "./WorkspaceLayout";

const API = "https://testserver/api/v1";
const PID = "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c";
const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });
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
const checkin = (id: string, week: string, over: Partial<Checkin> = {}): Checkin => ({
  id, member_id: "m2", member: { id: "dev", name: "Nusrat Jahan" }, week_start: week,
  done: "Stock table", next: "Filters", blockers: null, confidence: 4, on_time: true,
  created_at: `${week}T06:00:00Z`, reply_count: 0, ...over,
}); // prettier-ignore
const feed = (items: Checkin[], posted: boolean) => ({
  items,
  next_cursor: null,
  this_week: {
    week_start: "2026-11-23",
    due_at: "2026-11-24T17:59:59.999999Z",
    posted,
    missing: posted ? [] : [{ id: "dev", name: "Nusrat Jahan" }],
  },
});

function show(view: "member" | "client", items: Checkin[], posted: boolean) {
  server.use(
    csrf(),
    http.get(`${API}/projects/${PID}/team`, () => HttpResponse.json(team(view))),
    http.get(`${API}/projects/${PID}/checkins`, () => HttpResponse.json(feed(items, posted))),
  );
  renderRoutes(
    [
      {
        path: "/w/:projectId",
        element: (
          <>
            <WorkspaceLayout />
            <Toaster />
          </>
        ),
        children: [{ path: "check-ins", element: <CheckinsTab /> }],
      },
    ],
    `/w/${PID}/check-ins`,
  );
}

describe("CheckinsTab", () => {
  it("lets a member post this week's check-in", async () => {
    let sent: unknown = null;
    show("member", [], false);
    server.use(
      http.post(`${API}/projects/${PID}/checkins`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json(checkin("c1", "2026-11-23"), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/What did you finish/), "Stock table");
    await user.type(screen.getByLabelText(/What’s next/), "Filters");
    await user.click(screen.getByRole("button", { name: "Post check-in" }));
    expect(await screen.findByText("Checked in")).toBeInTheDocument();
    expect(sent).toEqual({ done: "Stock table", next: "Filters", blockers: null, confidence: 3 });
  });

  it("asks for the required parts before posting", async () => {
    show("member", [], false);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Post check-in" }));
    expect(await screen.findByText("Say what you finished")).toBeInTheDocument();
    expect(screen.getByText("Say what’s next")).toBeInTheDocument();
  });

  it("shows the feed by week, with late check-ins and blockers marked", async () => {
    show("member", [checkin("c1", "2026-11-23"),
                    checkin("c0", "2026-11-16", { on_time: false, blockers: "No API keys" })],
         true); // prettier-ignore
    expect(await screen.findByRole("heading", { name: "Week of 23 Nov 2026" })).toBeInTheDocument();
    const older = screen.getByRole("region", { name: "Week of 16 Nov 2026" });
    expect(within(older).getByText("Late")).toBeInTheDocument();
    expect(within(older).getByText("No API keys")).toBeInTheDocument();
    expect(screen.getByText("You checked in this week.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Post check-in" })).not.toBeInTheDocument();
  });

  it("gives the client no form, only the feed and who still owes one", async () => {
    show("client", [], false);
    expect(await screen.findByText("No check-ins yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Post check-in" })).not.toBeInTheDocument();
    expect(screen.getByText("Still to check in")).toBeInTheDocument();
  });
});

describe("check-in rules", () => {
  it("bounds every field", () => {
    const ok = { done: "a", next: "b", blockers: "", confidence: 1 };
    expect(checkinSchema.safeParse(ok).success).toBe(true);
    expect(checkinSchema.safeParse({ ...ok, done: " " }).success).toBe(false);
    expect(checkinSchema.safeParse({ ...ok, next: "x".repeat(2001) }).success).toBe(false);
    expect(checkinSchema.safeParse({ ...ok, confidence: 6 }).success).toBe(false);
    expect(checkinSchema.safeParse({ ...ok, done: "x".repeat(2000) }).success).toBe(true);
  });

  it("groups consecutive weeks", () => {
    const groups = byWeek([checkin("a", "2026-11-23"), checkin("b", "2026-11-23"),
                           checkin("c", "2026-11-16")]); // prettier-ignore
    expect(groups.map((g) => [g.week, g.items.length])).toEqual([
      ["2026-11-23", 2],
      ["2026-11-16", 1],
    ]);
  });
});
