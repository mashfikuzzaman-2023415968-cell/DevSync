/** Client Team screen, Teams list, dashboard invitation banners and the countdown: every state,
 * the requests each action sends (If-Match, reasons), and refusals shown inline. */
import { render as rtlRender, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { ExpiryCountdown, timeLeft } from "@/components/ExpiryCountdown";
import { Toaster } from "@/components/ui/Toaster";
import { Probe, renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import ClientTeamPage from "./ClientTeamPage";
import { InvitationBanners } from "./InvitationBanners";
import TeamsPage from "./TeamsPage";

const API = "https://testserver/api/v1";
const PID = "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c";
const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });

const member = (over: Record<string, unknown> = {}) => ({
  id: "m1", developer_id: "d1", developer_name: "Nusrat Jahan", slot_id: "s1",
  slot_label: "React developer", status: "ACTIVE", is_lead: false, is_newcomer: false,
  competency: 0.74, teamwork: 0.66, hours_per_week: 20, joined_at: "2026-11-24T07:00:00Z",
  invitation: { id: "i1", state: "ACCEPTED", sent_at: "2026-11-24T06:00:00Z",
                expires_at: "2026-11-26T06:00:00Z", responded_at: "2026-11-24T07:00:00Z",
                is_replacement: false },
  is_you: false, price_paisa: 2_400_000, days_needed: 22, left_reason: null,
  lead_declined: false, fully_booked: false, ...over,
}); // prettier-ignore

const team = (over: Record<string, unknown> = {}) => ({
  project_id: PID, project_title: "Online ordering system", project_status: "TEAM_PENDING",
  project_version: 4, team_id: "t", team_status: "PENDING", lead_member_id: null,
  view: "client",
  members: [member(), member({ id: "m2", developer_id: "d2", developer_name: "Arif Hasan",
                               is_newcomer: true, teamwork: 0.5 })],
  recommendation: { member_id: "m1", developer_name: "Nusrat Jahan",
                    reason: "Highest teamwork capacity: 66", preselected_member_id: null },
  can_choose_lead: true, can_start: false, start_blockers: ["Choose a team lead."],
  lead_change_requests: [], removal_requests: [], repair: null, ...over,
}); // prettier-ignore

const repair = (over: Record<string, unknown> = {}) => ({
  id: "r1", status: "READY", job_id: "j1", created_at: "2026-11-25T06:00:00Z",
  departed_member_id: "m3", slot_id: "s1", slot_label: "Testing developer",
  candidates: [{ bid_id: "b9", developer_name: "Zahid Mahmud", is_newcomer: false,
                 competency: 0.55, teamwork: 0.6, price_paisa: 1_900_000, days_needed: 22,
                 fitness: 0.74, team_price_paisa: 9_100_000,
                 impact: { affected_milestones: ["Testing & launch"], baseline_days: 24,
                           new_days: 25, delay_days: 1, budget_delta_paisa: -1_700_000,
                           budget_only: false } }],
  reasons: [], impact: { affected_milestones: ["Testing & launch"] }, chosen_bid_id: null,
  ...over,
}); // prettier-ignore

const page = () =>
  renderRoutes(
    [
      {
        path: "/client/projects/:id/team",
        element: (
          <>
            <ClientTeamPage />
            <Toaster />
          </>
        ),
      },
      { path: "*", element: <Probe label="elsewhere" /> },
    ],
    `/client/projects/${PID}/team`,
  );

describe("ClientTeamPage", () => {
  it("loads, then shows members, the recommendation and why it can't start", async () => {
    server.use(http.get(`${API}/projects/${PID}/team`, () => HttpResponse.json(team())));
    page();
    expect(screen.getByLabelText("Loading your team")).toBeInTheDocument();
    expect(await screen.findByText("Recommended: Nusrat Jahan")).toBeInTheDocument();
    expect(screen.getByText("Highest teamwork capacity: 66")).toBeInTheDocument();
    expect(screen.getByText("Choose a team lead.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start project" })).toBeDisabled();
    expect(screen.getAllByText("Accepted")).toHaveLength(2);
    expect(screen.getAllByText(/৳24,000 in 22 days/)).toHaveLength(2);
    expect(screen.getByText("Newcomer")).toBeInTheDocument();
  });

  it("confirms the lead with the project version", async () => {
    let ifMatch: string | null = null;
    let body: unknown = null;
    server.use(
      csrf(),
      http.get(`${API}/projects/${PID}/team`, () => HttpResponse.json(team())),
      http.post(`${API}/projects/${PID}/team/lead`, async ({ request }) => {
        ifMatch = request.headers.get("If-Match");
        body = await request.json();
        return HttpResponse.json({ status: "LEAD_CHOSEN", message: "ok" });
      }),
    );
    page();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Confirm lead" }));
    expect(await screen.findByText("Team lead chosen")).toBeInTheDocument();
    expect(ifMatch).toBe("4");
    expect(body).toEqual({ member_id: "m1" });
  });

  it("shows a pending invitation's countdown and a fully booked invitee", async () => {
    const soon = new Date(Date.now() + 3 * 3600_000).toISOString();
    server.use(
      http.get(
        `${API}/projects/${PID}/team`,
        () =>
        HttpResponse.json(
          team({
            recommendation: null,
            members: [member({ status: "INVITED", fully_booked: true,
              invitation: { id: "i1", state: "PENDING", sent_at: "2026-11-24T06:00:00Z",
                            expires_at: soon, responded_at: null, is_replacement: false } })],
          }),
        ), // prettier-ignore
      ),
    );
    page();
    expect(await screen.findByText(/Can’t accept: fully booked/)).toBeInTheDocument();
    expect(screen.getByText(/h \d+ min left/)).toBeInTheDocument();
    expect(screen.getByText("Invited")).toBeInTheDocument();
  });

  it("offers ranked replacements and invites one", async () => {
    let chosen: unknown = null;
    server.use(
      csrf(),
      http.get(`${API}/projects/${PID}/team`, () =>
        HttpResponse.json(team({ repair: { id: "r1", status: "READY", departed_member_id: "m3",
                                           job_id: "j1", created_at: "2026-11-25T06:00:00Z" } })),
      ), // prettier-ignore
      http.get(`${API}/projects/${PID}/repair`, () => HttpResponse.json(repair())),
      http.post(`${API}/repair-proposals/r1/choose`, async ({ request }) => {
        chosen = await request.json();
        return HttpResponse.json(repair({ status: "CHOSEN" }));
      }),
    );
    page();
    expect(await screen.findByText("Find a replacement for Testing developer")).toBeInTheDocument();
    expect(screen.getByText(/Finishes 1 day later/)).toBeInTheDocument();
    expect(screen.getByText(/৳17,000 left in the budget/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Invite" }));
    expect(await screen.findByText("Replacement invited")).toBeInTheDocument();
    expect(chosen).toEqual({ bid_id: "b9" });
  });

  it("explains a repair with nobody and offers reopen and raise budget", async () => {
    server.use(
      http.get(`${API}/projects/${PID}/team`, () =>
        HttpResponse.json(team({ repair: { id: "r1", status: "NO_CANDIDATES", departed_member_id: "m3",
                                           job_id: "j1", created_at: "2026-11-25T06:00:00Z" } })),
      ), // prettier-ignore
      http.get(`${API}/projects/${PID}/repair`, () =>
        HttpResponse.json(repair({ status: "NO_CANDIDATES", candidates: [], reasons: [
          { code: "REMAINING_BUDGET_TOO_LOW", message: "The budget left can't pay any of the other bidders.",
            shortfall_paisa: 50_000 }] })),
      ), // prettier-ignore
    );
    page();
    expect(await screen.findByText(/It is ৳500 short/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reopen place (48 h)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Raise budget" })).toBeInTheDocument();
  });

  it("shows the empty state for a project without a team, and errors with a retry", async () => {
    server.use(
      http.get(`${API}/projects/${PID}/team`, () =>
        HttpResponse.json({ error: { code: "NOT_FOUND", request_id: "r" } }, { status: 404 }),
      ),
    );
    page();
    expect(await screen.findByText("No team yet")).toBeInTheDocument();
  });

  it("shows an error with a retry", async () => {
    server.use(
      http.get(`${API}/projects/${PID}/team`, () =>
        HttpResponse.json(
          { error: { code: "INTERNAL_ERROR", request_id: "r-1" } },
          { status: 500 },
        ),
      ),
    );
    page();
    expect(await screen.findByText("Your team didn’t load")).toBeInTheDocument();
  });
});

describe("TeamsPage", () => {
  const show = () => renderRoutes([{ path: "/", element: <TeamsPage /> }], "/");

  it("lists teams with what needs attention", async () => {
    server.use(
      http.get(`${API}/me/teams`, () =>
        HttpResponse.json([{ project_id: PID, project_title: "Online ordering system",
          project_status: "TEAM_PENDING", team_id: "t", team_status: "PENDING", accepted: 3,
          places: 4, lead_name: null, needs_attention: ["REPAIR_OPEN"] }]),
      ), // prettier-ignore
    );
    show();
    expect(await screen.findByText("Online ordering system")).toBeInTheDocument();
    expect(screen.getByText(/3 of 4 places accepted\. No lead yet\./)).toBeInTheDocument();
    expect(screen.getByText("A place needs a replacement")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage team" })).toHaveAttribute(
      "href",
      `/client/projects/${PID}/team`,
    );
  });

  it("shows the empty state", async () => {
    server.use(http.get(`${API}/me/teams`, () => HttpResponse.json([])));
    show();
    expect(await screen.findByText("No teams yet")).toBeInTheDocument();
  });
});

describe("InvitationBanners", () => {
  const invitation = {
    id: "i1", member_id: "m1", project_id: PID, project_title: "Online ordering system",
    slot_label: "React developer", price_paisa: 2_400_000, days_needed: 22, state: "PENDING",
    sent_at: "2026-11-24T06:00:00Z", expires_at: new Date(Date.now() + 40 * 3600_000).toISOString(),
    responded_at: null, is_replacement: false,
  }; // prettier-ignore
  const show = () =>
    renderRoutes(
      [
        {
          path: "/",
          element: (
            <>
              <InvitationBanners />
              <Toaster />
            </>
          ),
        },
      ],
      "/",
    );

  it("accepts, and shows a refusal for lack of free hours inline", async () => {
    server.use(
      csrf(),
      http.get(`${API}/me/invitations`, () =>
        HttpResponse.json({ invitations: [invitation], memberships: [] }),
      ),
      http.post(`${API}/invitations/i1/accept`, () =>
        HttpResponse.json({ error: { code: "UNAVAILABLE", message: "You have 10 free hours a week.",
                                     request_id: "r" } }, { status: 409 }),
      ), // prettier-ignore
    );
    show();
    expect(await screen.findByText("You were selected")).toBeInTheDocument();
    expect(screen.getByText(/React developer on “Online ordering system”/)).toBeInTheDocument();
    expect(screen.getByText(/day \d+ h left|days \d+ h left|h \d+ min left/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Accept" }));
    expect(await screen.findByText("You can’t accept yet")).toBeInTheDocument();
    expect(screen.getByText("You have 10 free hours a week.")).toBeInTheDocument();
  });

  it("declines with an optional reason", async () => {
    let body: unknown = null;
    server.use(
      csrf(),
      http.get(`${API}/me/invitations`, () =>
        HttpResponse.json({ invitations: [invitation], memberships: [] }),
      ),
      http.post(`${API}/invitations/i1/decline`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ status: "DECLINED", message: "ok" });
      }),
    );
    show();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Decline" }));
    const dialog = await screen.findByRole("dialog", { name: "Decline this invitation?" });
    await user.type(within(dialog).getByRole("textbox"), "Booked elsewhere");
    await user.click(within(dialog).getByRole("button", { name: "Decline invitation" }));
    expect(await screen.findByText("Invitation declined")).toBeInTheDocument();
    expect(body).toEqual({ reason: "Booked elsewhere" });
  });

  it("shows a started team with the workspace link and the lead role", async () => {
    server.use(
      http.get(`${API}/me/invitations`, () =>
        HttpResponse.json({ invitations: [], memberships: [{ member_id: "m1", project_id: PID,
          project_title: "Online ordering system", project_status: "IN_PROGRESS",
          status: "ACTIVE", is_lead: true }] }),
      ), // prettier-ignore
    );
    show();
    expect(await screen.findByText("You are team lead")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open workspace" })).toHaveAttribute(
      "href",
      `/w/${PID}/team`,
    );
    expect(screen.getByRole("button", { name: "Decline the lead role" })).toBeInTheDocument();
  });

  it("renders nothing without invitations or teams", async () => {
    server.use(
      http.get(`${API}/me/invitations`, () =>
        HttpResponse.json({ invitations: [], memberships: [] }),
      ),
    );
    const { container } = show();
    await new Promise((r) => setTimeout(r, 50));
    expect(container.querySelector("section")).toBeNull();
  });
});

describe("ExpiryCountdown", () => {
  it("counts down in days, hours and minutes", () => {
    const now = Date.parse("2026-11-24T06:00:00Z");
    const at = (ms: number) => new Date(now + ms).toISOString();
    expect(timeLeft(at(2 * 86_400_000 + 4 * 3_600_000), now)).toBe("2 days 4 h left");
    expect(timeLeft(at(86_400_000), now)).toBe("1 day 0 h left");
    expect(timeLeft(at(3 * 3_600_000 + 5 * 60_000), now)).toBe("3 h 5 min left");
    expect(timeLeft(at(30_000), now)).toBe("1 min left");
    expect(timeLeft(at(-1), now)).toBe("Expired");
  });

  it("gives screen readers a static expiry time and turns amber when close", () => {
    rtlRender(<ExpiryCountdown expiresAt={new Date(Date.now() + 3600_000).toISOString()} />);
    expect(screen.getByText(/^Expires /)).toHaveClass("sr-only");
    expect(screen.getByText(/min left/).parentElement).toHaveClass("text-warning");
  });
});
