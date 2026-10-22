/** My Bids and the client Bids table (eligibility, too-few-bids banner). */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import ClientBidsPage from "./ClientBidsPage";
import MyBidsPage from "./MyBidsPage";

const API = "https://testserver/api/v1";
const PID = "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c";

function render(path: string, element: React.ReactNode, init: string) {
  return renderRoutes(
    [
      { path, element },
      { path: "*", element: <Probe label="elsewhere" /> },
    ],
    init,
  );
}

describe("MyBidsPage", () => {
  it("shows the empty state", async () => {
    server.use(http.get(`${API}/me/bids`, () => HttpResponse.json([])));
    render("/dev/bids", <MyBidsPage />, "/dev/bids");
    expect(await screen.findByText("No bids yet")).toBeInTheDocument();
  });

  it("lists bids with their status", async () => {
    server.use(
      http.get(`${API}/me/bids`, () =>
        HttpResponse.json([
          {
            id: "b1",
            project_id: PID,
            project_title: "Online ordering system",
            slot_id: "s",
            slot_label: "React",
            status: "ACTIVE",
            price_paisa: 1_800_000,
            days_needed: 20,
            proposal: "",
            expected_contribution: "",
            portfolio_item_ids: [],
            hours_per_week_committed: 20,
            created_at: "2026-10-21T06:00:00Z",
            updated_at: "2026-10-21T06:00:00Z",
          },
        ]),
      ),
    );
    render("/dev/bids", <MyBidsPage />, "/dev/bids");
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Online ordering system" })).toBeInTheDocument();
    expect(screen.getByText("React, ৳18,000 for 20 days")).toBeInTheDocument();
  });
});

describe("ClientBidsPage", () => {
  const checks = (failing?: string) =>
    [
      ["account_active", "Account active"],
      ["has_slot_skill", "Lists React"],
      ["no_conflict", "No conflict of interest"],
      ["available", "Enough free hours over the project period"],
      ["skill_evidence", "React test 85% (newcomers need 60%)"],
      ["days", failing === "days" ? "31 days (deadline 30 days)" : "20 days (deadline 30 days)"],
      ["price", "৳18,000 (budget after fee ৳114,000)"],
    ].map(([name, detail]) => ({
      name,
      ok: name !== failing,
      detail,
      required: null,
      actual: null,
    }));

  const bid = (over: Record<string, unknown>) => ({
    id: "b1",
    developer_id: "d1",
    developer_name: "Nadia Rahman",
    slot_id: "s1",
    slot_label: "React developer",
    status: "ACTIVE",
    price_paisa: 1_800_000,
    days_needed: 20,
    hours_per_week: 20,
    competency: 0.31,
    teamwork: 0.5,
    performance: 0.55,
    is_newcomer: true,
    seeded: false,
    eligible: true,
    shortlisted: true,
    reasons: [],
    checks: checks(),
    newcomer_evidence: { skill: "React", score: 0.85 },
    proposal: "React front end with tests.",
    expected_contribution: "Components and integration.",
    portfolio: [{ id: "p1", title: "Kitchen orders app" }],
    submitted_at: "2026-10-21T06:00:00Z",
    ...over,
  });

  const view = (over: Record<string, unknown> = {}) => ({
    bids: [
      bid({}),
      bid({
        id: "b2",
        developer_id: "d2",
        developer_name: "Shakib Hasan",
        is_newcomer: false,
        eligible: false,
        shortlisted: false,
        reasons: ["TOO_SLOW"],
        days_needed: 31,
        checks: checks("days"),
        newcomer_evidence: null,
        portfolio: [],
      }),
    ],
    coverage: [{ slot_id: "s1", slot_label: "React developer", needed: 2, eligible: 1 }],
    relaxations: [{ step: 1, p0: 0.4, c0: 0.35 }],
    too_few: true,
    evaluated_at: "2026-10-22T06:00:00Z",
    thresholds: {
      p0: 0.45,
      c0: 0.4,
      default_p0: 0.45,
      default_c0: 0.4,
      floor_p0: 0.3,
      floor_c0: 0.25,
      used_p0: 0.4,
      used_c0: 0.35,
    },
    team_cost: { total_paisa: 1_800_000, budget_after_fee_paisa: 11_400_000, complete: false },
    budget_paisa: 12_000_000,
    team_size: 2,
    bidding: {
      deadline: "2026-10-25T06:00:00Z",
      closed: false,
      extensions_used: 0,
      max_extensions: 2,
      extend_days: 3,
      closes_automatically_at: "2026-11-08T06:00:00Z",
    },
    ...over,
  });

  function serve(data: object, status = "BIDDING") {
    server.use(
      http.get(`${API}/projects/${PID}/bids`, () => HttpResponse.json(data)),
      http.get(`${API}/projects/${PID}`, () =>
        HttpResponse.json({ id: PID, title: "Online ordering system", status, version: 3 }),
      ),
    );
  }

  const page = () =>
    render("/client/projects/:id/bids", <ClientBidsPage />, `/client/projects/${PID}/bids`);

  it("shows verdicts, coverage, the cheapest team, relaxation and the too-few banner", async () => {
    serve(view());
    page();
    expect(await screen.findByText("Not enough eligible bids yet")).toBeInTheDocument();
    expect(screen.getByText(/React developer needs 1 more eligible bid/)).toBeInTheDocument();
    expect(screen.getByText(/lowered from 45 to 40.*step 1 of 3/)).toBeInTheDocument();
    expect(screen.getByText("Not every place can be filled yet.")).toBeInTheDocument();
    expect(screen.getByText(/closes on its own on 8 Nov 2026/)).toBeInTheDocument();
    expect(screen.getByText(/2 bids, 1 eligible/)).toBeInTheDocument();
    const nadia = screen.getByRole("row", { name: /Nadia Rahman/ });
    expect(within(nadia).getByText("Eligible")).toBeInTheDocument();
    expect(within(nadia).getByText("Newcomer")).toBeInTheDocument();
    const shakib = screen.getByRole("row", { name: /Shakib Hasan/ });
    expect(within(shakib).getByText("Can’t meet the deadline")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Fix the shortfall" })).toBeInTheDocument();
  });

  it("explains a verdict check by check", async () => {
    serve(view());
    page();
    const user = userEvent.setup();
    const [why] = await screen.findAllByRole("button", { name: "Why not eligible: Shakib Hasan" });
    await user.click(why as HTMLElement);
    const sheet = await screen.findByRole("dialog", { name: "Shakib Hasan" });
    expect(
      within(sheet).getByText("Filtered out: 31 days (deadline 30 days)."),
    ).toBeInTheDocument();
    expect(within(sheet).getByText("Finishes within the deadline")).toBeInTheDocument();
    expect(within(sheet).getAllByText(": met").length).toBeGreaterThan(0);
    expect(within(sheet).getByText(": not met")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    const [nadia] = screen.getAllByRole("button", { name: "Why eligible: Nadia Rahman" });
    await user.click(nadia as HTMLElement);
    const second = await screen.findByRole("dialog", { name: "Nadia Rahman" });
    expect(
      within(second).getByText("Eligible through the newcomer rule: React test 85%."),
    ).toBeInTheDocument();
    expect(within(second).getByText("Kitchen orders app")).toBeInTheDocument();
    expect(within(second).getByText("React front end with tests.")).toBeInTheDocument();
  });

  it("filters by eligibility", async () => {
    serve(view());
    page();
    const user = userEvent.setup();
    await screen.findByRole("row", { name: /Nadia Rahman/ });
    await user.click(screen.getByRole("radio", { name: "Not eligible" }));
    expect(screen.queryByRole("row", { name: /Nadia Rahman/ })).not.toBeInTheDocument();
    expect(screen.getByRole("row", { name: /Shakib Hasan/ })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Eligible" }));
    expect(screen.queryByRole("row", { name: /Shakib Hasan/ })).not.toBeInTheDocument();
  });

  it("previews then applies a higher budget", async () => {
    serve(view());
    let previewed: unknown = null;
    let applied: unknown = null;
    server.use(
      http.get(`${API}/auth/csrf`, () => {
        document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
        return new HttpResponse(null, { status: 204 });
      }),
      http.post(`${API}/projects/${PID}/bidding-terms/preview`, async ({ request }) => {
        previewed = await request.json();
        const outcome = (eligible: number, tooFew: boolean) => ({
          eligible,
          too_few: tooFew,
          coverage: [],
          team_cost: {
            total_paisa: 3_000_000,
            budget_after_fee_paisa: 13_300_000,
            complete: !tooFew,
          },
        });
        return HttpResponse.json({
          before: outcome(1, true),
          after: outcome(2, false),
          newly_eligible: 1,
          message: "1 more bid would be eligible; every slot would be covered.",
        });
      }),
      http.patch(`${API}/projects/${PID}/bidding-terms`, async ({ request }) => {
        applied = await request.json();
        return HttpResponse.json(view({ too_few: false, budget_paisa: 14_000_000 }));
      }),
    );
    page();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Fix the shortfall" }));
    const dialog = await screen.findByRole("dialog", { name: "Fix the shortfall" });
    await user.click(within(dialog).getByRole("tab", { name: "Raise budget" }));
    const apply = within(dialog).getByRole("button", { name: "Raise the budget" });
    expect(apply).toBeDisabled(); // not raised yet
    const input = within(dialog).getByLabelText("New budget (৳)");
    await user.clear(input);
    await user.type(input, "140000");
    expect(
      await within(dialog).findByText(
        "1 more bid would be eligible; every slot would be covered.",
        {},
        { timeout: 3000 },
      ),
    ).toBeInTheDocument();
    expect(previewed).toEqual({ budget_paisa: 14_000_000 });
    await user.click(apply);
    await waitFor(() => {
      expect(applied).toEqual({ budget_paisa: 14_000_000 });
    });
    // Applied: the dialog closes and the page shows the fresh view (no longer short).
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Fix the shortfall" })).not.toBeInTheDocument();
    });
  });

  it("states the floors for lowering the standards and blocks spent extensions", async () => {
    serve(
      view({
        bidding: {
          deadline: "2026-10-20T06:00:00Z",
          closed: true,
          extensions_used: 2,
          max_extensions: 2,
          extend_days: 3,
        },
      }),
    );
    page();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Fix the shortfall" }));
    const dialog = await screen.findByRole("dialog", { name: "Fix the shortfall" });
    expect(
      within(dialog).getByText(/You can extend 0 more times \(2 of 2 used\)/),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /Extend bidding by 3 days/ })).toBeDisabled();
    await user.click(within(dialog).getByRole("tab", { name: "Lower standards" }));
    expect(
      within(dialog).getByText(/down to 30 for performance and 25 for competency/),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Lower the standards" })).toBeDisabled();
  });

  it("offers no fixes once the project has left bidding", async () => {
    serve(view(), "FORMING");
    page();
    expect(await screen.findByText("Not enough eligible bids yet")).toBeInTheDocument();
    await screen.findByText(/On “Online ordering system”/);
    expect(screen.queryByRole("button", { name: "Fix the shortfall" })).not.toBeInTheDocument();
  });

  it("shows an empty state when there are no bids", async () => {
    serve(view({ bids: [], coverage: [], relaxations: [], too_few: false }));
    page();
    expect(await screen.findByText("No bids yet")).toBeInTheDocument();
  });
});
