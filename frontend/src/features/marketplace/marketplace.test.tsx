/** Marketplace: Find Projects (filters, results) and the project bid sheet with live eligibility. */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import FindProjectsPage from "./FindProjectsPage";
import ProjectBidPage from "./ProjectBidPage";

const API = "https://testserver/api/v1";
const PID = "7a0f6b2c-1d3e-4f5a-8b6c-9d0e1f2a3b4c";
const SLOT = "0b7d4c1e-2f3a-4b5c-8d9e-0f1a2b3c4d5e";
const SKILLS = [{ id: "s-react", name: "React", domain: "FRONTEND" }];

const CARD = {
  id: PID,
  title: "Online ordering system",
  summary: "Order and track restaurant orders.",
  status: "BIDDING",
  budget_paisa: 12_000_000,
  deadline_days: 30,
  team_size: 4,
  bidding_deadline: null,
  skills: ["React", "FastAPI"],
  created_at: "2026-10-20T06:00:00Z",
};
const DETAIL = {
  ...CARD,
  requirements: "React front end, FastAPI back end.",
  slots: [{ id: SLOT, label: "React developer", skill: "React", skill_id: "s-react", count: 1 }],
};

function routes(path: string, element: React.ReactNode, init: string) {
  return renderRoutes(
    [
      { path, element },
      { path: "*", element: <Probe label="elsewhere" /> },
    ],
    init,
  );
}

describe("FindProjectsPage", () => {
  it("shows search results and the recommended strip", async () => {
    server.use(
      http.get(`${API}/skills`, () => HttpResponse.json(SKILLS)),
      http.get(`${API}/projects/recommended`, () =>
        HttpResponse.json([{ project: CARD, skill_match_count: 2 }]),
      ),
      http.get(`${API}/projects/search`, () =>
        HttpResponse.json({ items: [CARD], next_cursor: null }),
      ),
    );
    routes("/dev/find", <FindProjectsPage />, "/dev/find");
    expect(await screen.findByText("Recommended for you")).toBeInTheDocument();
    // The project appears in the results list (and the recommended strip).
    expect(screen.getAllByText("Online ordering system").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("No projects match")).not.toBeInTheDocument();
    expect(screen.getByText("Order and track restaurant orders.")).toBeInTheDocument();
  });

  it("keeps the search text in the URL", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${API}/skills`, () => HttpResponse.json(SKILLS)),
      http.get(`${API}/projects/recommended`, () => HttpResponse.json([])),
      http.get(`${API}/projects/search`, () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    const { router } = routes("/dev/find", <FindProjectsPage />, "/dev/find");
    await user.type(await screen.findByLabelText("Search"), "ordering");
    await waitFor(() => {
      expect(router.state.location.search).toContain("q=ordering");
    });
    expect(await screen.findByText("No projects match")).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    server.use(
      http.get(`${API}/skills`, () => HttpResponse.json(SKILLS)),
      http.get(`${API}/projects/recommended`, () => HttpResponse.json([])),
      http.get(`${API}/projects/search`, () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    routes("/dev/find", <FindProjectsPage />, "/dev/find");
    expect(await screen.findByText("No projects match")).toBeInTheDocument();
  });
});

describe("ProjectBidPage", () => {
  function base() {
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.get(`${API}/public/projects/${PID}`, () => HttpResponse.json(DETAIL)),
      http.get(`${API}/me/bids`, () => HttpResponse.json([])),
    );
  }

  it("shows the live eligibility preview and places a bid", async () => {
    const user = userEvent.setup();
    base();
    let posted: unknown = null;
    server.use(
      http.post(`${API}/projects/${PID}/bids/eligibility`, () =>
        HttpResponse.json({
          eligible: false,
          reason: "TOO_SLOW",
          message: "Would be filtered out: needs more days than the deadline allows.",
          checks: [{ name: "days", ok: false, detail: "31 of 30 days" }],
        }),
      ),
      http.post(`${API}/projects/${PID}/bids`, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json({ id: "b1", status: "ACTIVE" });
      }),
    );
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);

    expect(await screen.findByText("Online ordering system")).toBeInTheDocument();
    // Choose the role, enter a slow bid → live preview warns.
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: /React/ }));
    await user.type(screen.getByLabelText(/Your price/), "20000");
    await user.type(screen.getByLabelText(/Days you need/), "31");
    expect(await screen.findByText(/would be filtered out/i, {}, { timeout: 3000 })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Place sealed bid/ }));
    await waitFor(() => {
      expect(posted).toMatchObject({ slot_id: SLOT, days_needed: 31, price_paisa: 2_000_000 });
    });
  });

  it("shows an existing bid with a withdraw action", async () => {
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.get(`${API}/public/projects/${PID}`, () => HttpResponse.json(DETAIL)),
      http.get(`${API}/me/bids`, () =>
        HttpResponse.json([
          { id: "b1", project_id: PID, slot_id: SLOT, status: "ACTIVE", price_paisa: 1_800_000, days_needed: 20, proposal: "", expected_contribution: "", portfolio_item_ids: [], hours_per_week_committed: 20, created_at: "2026-10-21T06:00:00Z", updated_at: "2026-10-21T06:00:00Z" },
        ]),
      ),
    );
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);
    expect(await screen.findByText("Your bid")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Withdraw bid/ })).toBeInTheDocument();
  });
});
