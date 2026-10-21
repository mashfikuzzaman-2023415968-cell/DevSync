/** My Bids and the client Bids table (eligibility, too-few-bids banner). */
import { screen, within } from "@testing-library/react";
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
            slot_id: "s",
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
    expect(screen.getByRole("link", { name: "View project" })).toBeInTheDocument();
  });
});

describe("ClientBidsPage", () => {
  const bid = (over: Record<string, unknown>) => ({
    id: "b1",
    developer_id: "d1",
    developer_name: "Nadia Rahman",
    slot_id: "s1",
    slot_label: "React developer",
    status: "ACTIVE",
    price_paisa: 1_800_000,
    days_needed: 20,
    competency: 0.53,
    performance: 0.55,
    is_newcomer: true,
    seeded: false,
    eligible: true,
    reasons: [],
    ...over,
  });

  it("shows bids with eligibility and the too-few banner", async () => {
    server.use(
      http.get(`${API}/projects/${PID}/bids`, () =>
        HttpResponse.json({
          bids: [
            bid({}),
            bid({
              id: "b2",
              developer_name: "Shakib Hasan",
              is_newcomer: false,
              eligible: false,
              reasons: ["TOO_SLOW"],
              days_needed: 31,
            }),
          ],
          coverage: [{ slot_id: "s1", slot_label: "React developer", needed: 1, eligible: 1 }],
          relaxations: [{ step: 1, p0: 0.4, c0: 0.35 }],
          too_few: true,
        }),
      ),
    );
    render("/client/projects/:id/bids", <ClientBidsPage />, `/client/projects/${PID}/bids`);

    expect(await screen.findByText("Not enough eligible bids yet")).toBeInTheDocument();
    const eligibleRow = screen.getByRole("row", { name: /Nadia Rahman/ });
    expect(within(eligibleRow).getByText("Eligible")).toBeInTheDocument();
    expect(within(eligibleRow).getByText("Newcomer")).toBeInTheDocument();
    const slowRow = screen.getByRole("row", { name: /Shakib Hasan/ });
    expect(within(slowRow).getByText(/Too slow/)).toBeInTheDocument();
  });

  it("shows an empty state when there are no bids", async () => {
    server.use(
      http.get(`${API}/projects/${PID}/bids`, () =>
        HttpResponse.json({ bids: [], coverage: [], relaxations: [], too_few: false }),
      ),
    );
    render("/client/projects/:id/bids", <ClientBidsPage />, `/client/projects/${PID}/bids`);
    expect(await screen.findByText("No bids yet")).toBeInTheDocument();
  });
});
