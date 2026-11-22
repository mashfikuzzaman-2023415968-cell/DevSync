/** Team formation screen, its components and the "why not selected" card: every state (loading,
 * error, empty, running, result, infeasible, confirmed), the request a run sends, the weights that
 * always total 100 %, confirm, and the bidder's explanation. */
import { act, fireEvent, render as rtlRender, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { ConvergenceChart } from "@/components/ConvergenceChart";
import { FairnessDial } from "@/components/FairnessDial";
import { rebalance, toPercents } from "@/components/PrioritySliders";
import { Toaster } from "@/components/ui/Toaster";
import { Probe, renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import { WhyNotSelectedCard } from "@/features/bids/WhyNotSelectedCard";
import FormationPage, { PRESET_WEIGHTS } from "./FormationPage";

const API = "https://testserver/api/v1";
const PID = "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c";
const RUN = "5f0c2b7e-3d4a-4e8b-9c1d-2a3b4c5d6e7f";

const bid = (over: Record<string, unknown> = {}) => ({
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
  checks: [],
  newcomer_evidence: null,
  proposal: "",
  expected_contribution: "",
  portfolio: [],
  submitted_at: "2026-10-21T06:00:00Z",
  ...over,
});

const bidsView = (bids = [bid(), bid({ id: "b2", developer_id: "d2", developer_name: "Arif Hasan", is_newcomer: false, competency: 0.7, performance: 0.8 }), bid({ id: "b3", developer_id: "d3", developer_name: "Rumana Akter", is_newcomer: false, competency: 0.5, performance: 0.42 })]) => ({
  bids,
  coverage: [],
  relaxations: [],
  too_few: false,
  evaluated_at: "2026-10-22T06:00:00Z",
  thresholds: { p0: 0.45, c0: 0.4, default_p0: 0.45, default_c0: 0.4, floor_p0: 0.3,
    floor_c0: 0.25, used_p0: 0.45, used_c0: 0.4 },
  team_cost: { total_paisa: 3_600_000, budget_after_fee_paisa: 10_800_000, complete: true },
  budget_paisa: 12_000_000,
  team_size: 2,
  bidding: { deadline: "2026-10-25T06:00:00Z", closed: true, extensions_used: 0, max_extensions: 2,
    extend_days: 3, closes_automatically_at: null },
}); // prettier-ignore

const member = (over: Record<string, unknown> = {}) => ({
  bid_id: "b2",
  developer_id: "d2",
  developer_name: "Arif Hasan",
  slot_id: "s1",
  slot_label: "React developer",
  price_paisa: 2_400_000,
  days_needed: 18,
  is_newcomer: false,
  competency: 0.7,
  teamwork: 0.66,
  contribution: { comp: 0.245, team: 0.165, time: 0.08, cost: 0.04, perf: 0, total: 0.53 },
  ...over,
});

const result = (over: Record<string, unknown> = {}) => ({
  feasible: true,
  team: [member(), member({ bid_id: "b1", developer_id: "d1", developer_name: "Nadia Rahman", is_newcomer: true })],
  fitness: 0.9412,
  price_paisa: 4_200_000,
  budget_after_fee_paisa: 10_800_000,
  budget_share: 0.389,
  max_days: 20,
  deadline_days: 30,
  schedule_share: 0.667,
  newcomers: 1,
  risks: ["NEWCOMER_ON_CRITICAL_PATH"],
  deciding_term: "cost",
  runner_up_difference: { comp: -0.02, team: 0, time: 0.01, cost: 0.04 },
  verification: { available: true, reason: null, optimal: true, gap: 0, exact_fitness: 0.9412, feasible_count: 3 },
  fairness: { requested_k: 1, applied_k: 1, cost: 0.0213, binding: true, price_difference_paisa: -500_000, baseline_fitness: 0.9617, reason: null },
  top: [
    { bid_ids: ["b1", "b2"], fitness: 0.9412, price_paisa: 4_200_000, newcomers: 1, mean_competency: 0.5, mean_teamwork: 0.58, max_days: 20, recommended: true },
    { bid_ids: ["b2", "b3"], fitness: 0.9617, price_paisa: 4_700_000, newcomers: 0, mean_competency: 0.6, mean_teamwork: 0.6, max_days: 22, recommended: false },
  ],
  convergence: [0.9, 0.93, 0.9412],
  iterations: 41,
  early_stopped: true,
  timed_out: false,
  candidates: 3,
  relaxations: [],
  ...over,
}); // prettier-ignore

const run = (over: Record<string, unknown> = {}) => ({
  id: RUN,
  project_id: PID,
  status: "SUCCEEDED",
  job_id: "j1",
  seed: 7,
  settings_version: 5,
  params: { preset: "balanced", weights: { competency: 0.35, teamwork: 0.25, time: 0.2, cost: 0.2 },
    min_newcomers: 1, min_performance: 0.45, min_competency: 0.4, mode: "devsync" },
  result: result(),
  error_code: null,
  runtime_ms: 400,
  created_at: "2026-11-22T06:00:00Z",
  started_at: "2026-11-22T06:00:00Z",
  finished_at: "2026-11-22T06:00:01Z",
  confirmed: false,
  can_confirm: true,
  ...over,
}); // prettier-ignore

const summary = (over: Record<string, unknown> = {}) => ({
  id: RUN, project_id: PID, status: "SUCCEEDED", preset: "balanced", min_newcomers: 1,
  fitness: 0.9412, optimal: true, price_paisa: 4_200_000, created_at: "2026-11-22T06:00:00Z",
  finished_at: "2026-11-22T06:00:01Z", confirmed: false, ...over,
}); // prettier-ignore

function serve({
  status = "FORMING",
  runs = [] as object[],
  current = run(),
}: { status?: string; runs?: object[]; current?: object } = {}) {
  server.use(
    http.get(`${API}/projects/${PID}`, () =>
      HttpResponse.json({ id: PID, title: "Online ordering system", status, version: 3 }),
    ),
    http.get(`${API}/projects/${PID}/bids`, () => HttpResponse.json(bidsView())),
    http.get(`${API}/projects/${PID}/formation-runs`, () => HttpResponse.json(runs)),
    http.get(`${API}/formation-runs/${RUN}`, () => HttpResponse.json(current)),
    http.get("*/api/v1/auth/csrf", () => {
      document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
      return new HttpResponse(null, { status: 204 });
    }),
  );
}

const page = () =>
  renderRoutes(
    [
      {
        path: "/client/projects/:id/formation",
        element: (
          <>
            <FormationPage />
            <Toaster />
          </>
        ),
      },
      { path: "*", element: <Probe label="elsewhere" /> },
    ],
    `/client/projects/${PID}/formation`,
  );

describe("priority weights", () => {
  it("always total 100 and follow the presets", () => {
    for (const p of Object.values(PRESET_WEIGHTS)) {
      const w = toPercents(p);
      expect(w.competency + w.teamwork + w.time + w.cost).toBe(100);
    }
    expect(toPercents(PRESET_WEIGHTS.balanced)).toEqual({
      competency: 35,
      teamwork: 25,
      time: 20,
      cost: 20,
    });
    const moved = rebalance({ competency: 35, teamwork: 25, time: 20, cost: 20 }, "cost", 60);
    expect(moved.cost).toBe(60);
    expect(moved.competency + moved.teamwork + moved.time + moved.cost).toBe(100);
    expect(moved.competency).toBeGreaterThan(moved.time); // in proportion
    const all = rebalance({ competency: 0, teamwork: 0, time: 0, cost: 100 }, "cost", 40);
    expect(all).toEqual({ competency: 20, teamwork: 20, time: 20, cost: 40 });
    expect(rebalance(moved, "time", 150).time).toBe(100);
    expect(rebalance(moved, "time", -5).time).toBe(0);
  });
});

describe("FairnessDial", () => {
  it("offers only as many newcomers as were shortlisted and shows the cost", () => {
    rtlRender(
      <FairnessDial value="1" onChange={() => undefined} newcomersAvailable={1} cost={0.032} />,
    );
    expect(screen.getByRole("radio", { name: "1" })).toBeChecked();
    expect(screen.queryByRole("radio", { name: "2" })).not.toBeInTheDocument();
    expect(screen.getByText("Cost of fairness 3.2%")).toBeInTheDocument();
  });

  it("explains a dial with no newcomers", () => {
    rtlRender(<FairnessDial value="1" onChange={() => undefined} newcomersAvailable={0} />);
    expect(screen.getByRole("radio", { name: "0" })).toBeChecked();
    expect(screen.getByText(/chosen on merit alone/)).toBeInTheDocument();
  });
});

describe("ConvergenceChart", () => {
  it("summarises the best score and has a table view", async () => {
    rtlRender(<ConvergenceChart values={[null, 0.5, 0.71]} iterations={30} />);
    expect(screen.getByText("Best team score 0.7100 after 30 iterations.")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("radio", { name: "View as table" }));
    const table = screen.getByRole("table", { name: "Best team score by iteration" });
    expect(within(table).getByText("No team yet")).toBeInTheDocument();
    expect(within(table).getByText("0.7100")).toBeInTheDocument();
  });

  it("says when nothing was found yet", () => {
    rtlRender(<ConvergenceChart values={[]} iterations={0} live />);
    expect(screen.getByText("No team found yet.")).toBeInTheDocument();
  });
});

describe("FormationPage", () => {
  it("shows a loading skeleton, then the first-run empty state", async () => {
    serve();
    page();
    expect(screen.getByLabelText("Loading team formation")).toBeInTheDocument();
    expect(await screen.findByText("No team yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Form team" })).toBeInTheDocument();
    expect(screen.getByText(/2 of 3 bids meet these standards/)).toBeInTheDocument();
  });

  it("shows an error with a retry", async () => {
    serve();
    server.use(
      http.get(`${API}/projects/${PID}/formation-runs`, () =>
        HttpResponse.json(
          { error: { code: "INTERNAL_ERROR", request_id: "r-7" } },
          { status: 500 },
        ),
      ),
    );
    page();
    expect(await screen.findByText("Team formation didn’t load")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Try again/ })).toBeInTheDocument();
  });

  it("explains that bidding is still open", async () => {
    serve({ status: "BIDDING" });
    page();
    expect(await screen.findByText("Bidding is still open")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Form team" })).not.toBeInTheDocument();
  });

  it("sends the preset and dial, never a seed, and follows the run", async () => {
    serve();
    let sent: Record<string, unknown> | null = null;
    let key: string | null = null;
    server.use(
      http.post(`${API}/projects/${PID}/formation-runs`, async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        key = request.headers.get("Idempotency-Key");
        server.use(
          http.get(`${API}/projects/${PID}/formation-runs`, () => HttpResponse.json([summary()])),
        );
        return HttpResponse.json(
          { run_id: RUN, job_id: "j1", status: "QUEUED", progress: 0 },
          { status: 202 },
        );
      }),
    );
    page();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "Budget" }));
    await user.click(screen.getByRole("button", { name: "Form team" }));
    expect(await screen.findByText("Optimal (exact check)")).toBeInTheDocument();
    expect(sent).toEqual({ preset: "budget", min_newcomers: 1 });
    expect(key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("sends custom weights and standards when they are changed", async () => {
    serve();
    let sent: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API}/projects/${PID}/formation-runs`, async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { error: { code: "LIMIT_REACHED", message: "A team formation run is already in progress for this project.", request_id: "r" } },
          { status: 409 },
        ); // prettier-ignore
      }),
    );
    page();
    const user = userEvent.setup();
    const cost = await screen.findByRole("slider", { name: "Cost" });
    act(() => {
      cost.focus();
    });
    fireEvent.keyDown(cost, { key: "ArrowRight" });
    const performance = screen.getByRole("slider", { name: "Performance" });
    fireEvent.keyDown(performance, { key: "ArrowRight" });
    await user.click(screen.getByRole("button", { name: "Form team" }));
    expect(await screen.findByText("The team search didn’t start")).toBeInTheDocument();
    expect(screen.getByText(/already in progress/)).toBeInTheDocument();
    expect(sent).toMatchObject({
      preset: "balanced",
      weights: { cost: "0.210" },
      min_performance: "0.460",
    });
    expect(sent).not.toHaveProperty("min_competency");
    expect(sent).not.toHaveProperty("seed");
  });

  it("shows the result: stats, members, why, comparison, and confirms", async () => {
    serve({ runs: [summary()] });
    let confirmed = false;
    server.use(
      http.post(`${API}/formation-runs/${RUN}/confirm`, () => {
        confirmed = true;
        return HttpResponse.json({ team_id: "t", project_status: "TEAM_PENDING", members: 2,
          invitations_sent: false }); // prettier-ignore
      }),
    );
    page();
    const user = userEvent.setup();
    expect(await screen.findByText("Optimal (exact check)")).toBeInTheDocument();
    expect(screen.getAllByText("0.94").length).toBeGreaterThan(0);
    expect(screen.getByText("৳42,000")).toBeInTheDocument();
    expect(screen.getByText("2.1%")).toBeInTheDocument();
    expect(screen.getByText("1 newcomer included")).toBeInTheDocument();
    expect(screen.getAllByText("Newcomer").length).toBeGreaterThan(0);
    expect(screen.getByText(/mainly for its cost/)).toBeInTheDocument();
    expect(screen.getByText(/A newcomer works on a critical milestone/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Compare" }));
    expect(screen.getAllByText("Recommended").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Confirm team" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Confirm this team?" });
    await user.click(within(dialog).getByRole("button", { name: "Confirm team" }));
    expect(await screen.findByText("Team confirmed")).toBeInTheDocument();
    expect(confirmed).toBe(true);
  });

  it("shows the running state with the swarm", async () => {
    serve({
      runs: [summary({ status: "RUNNING", fitness: null })],
      current: run({ status: "RUNNING", result: null, can_confirm: false }),
    });
    page();
    expect(await screen.findByText("Searching for the best team…")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Search progress" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recalculate" })).toBeDisabled();
  });

  it("explains an infeasible run and a capped dial", async () => {
    serve({
      runs: [summary({ status: "INFEASIBLE", fitness: null })],
      current: run({
        status: "INFEASIBLE",
        result: result({ feasible: false, team: [] }),
        can_confirm: false,
      }),
    });
    page();
    expect(await screen.findByText("No team fits every requirement")).toBeInTheDocument();
  });

  it("shows a confirmed team read-only", async () => {
    serve({
      status: "TEAM_PENDING",
      runs: [summary({ confirmed: true })],
      current: run({ confirmed: true, can_confirm: false }),
    });
    page();
    expect(await screen.findByText("Team confirmed")).toBeInTheDocument();
    expect(await screen.findByText("Optimal (exact check)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm team" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Recalculate" })).not.toBeInTheDocument();
  });
});

describe("WhyNotSelectedCard", () => {
  const explanation = (over: Record<string, unknown> = {}) => ({
    bid_id: "b3", project_title: "Online ordering system", reasons: ["NOT_SELECTED"],
    main_gap: "cost", hint: "A lower price would have helped most.", gap: 0.04,
    price_counterfactual_paisa: 1_600_000,
    compare: { selected_days: 18, selected_price_paisa: 1_700_000, your_days: 20, your_price_paisa: 2_000_000 },
    created_at: "2026-11-22T06:05:00Z", ...over,
  }); // prettier-ignore
  const show = () => renderRoutes([{ path: "/", element: <WhyNotSelectedCard bidId="b3" /> }], "/");

  it("gives the main gap, the concrete comparison and the counterfactual price", async () => {
    server.use(http.get(`${API}/bids/b3/explanation`, () => HttpResponse.json(explanation())));
    show();
    expect(await screen.findByText("Price made the biggest difference")).toBeInTheDocument();
    expect(
      screen.getByText("The selected bid for this role is ৳17,000; yours is ৳20,000."),
    ).toBeInTheDocument();
    expect(screen.getByText("৳16,000")).toBeInTheDocument();
    expect(screen.getByText(/or less, you would have been selected/)).toBeInTheDocument();
  });

  it("says when a lower price alone wouldn’t have helped", async () => {
    server.use(
      http.get(`${API}/bids/b3/explanation`, () =>
        HttpResponse.json(
          explanation({
            main_gap: "time",
            price_counterfactual_paisa: null,
            hint: "A shorter delivery time would have helped most.",
          }),
        ),
      ),
    );
    show();
    expect(
      await screen.findByText("The selected bid for this role needs 18 days; yours needs 20 days."),
    ).toBeInTheDocument();
    expect(screen.getByText(/A lower price alone/)).toBeInTheDocument();
  });

  it("is patient while the explanation is prepared, and shows errors", async () => {
    server.use(
      http.get(`${API}/bids/b3/explanation`, () =>
        HttpResponse.json({ error: { code: "NOT_FOUND", request_id: "r" } }, { status: 404 }),
      ),
    );
    show();
    expect(await screen.findByText(/being prepared/)).toBeInTheDocument();
  });

  it("shows a retry when it fails", async () => {
    server.use(
      http.get(`${API}/bids/b3/explanation`, () =>
        HttpResponse.json(
          { error: { code: "INTERNAL_ERROR", request_id: "r-2" } },
          { status: 500 },
        ),
      ),
    );
    show();
    expect(await screen.findByText("The explanation didn’t load")).toBeInTheDocument();
  });
});
