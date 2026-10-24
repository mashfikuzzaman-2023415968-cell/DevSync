/** Marketplace: Find Projects (filters, results) and the project bid sheet with live eligibility. */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, type JsonBodyType } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
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
  open_for_bids: true,
};
const DETAIL = {
  ...CARD,
  description: "Customers order online; the kitchen sees each order live.",
  requirements: "React front end, FastAPI back end.",
  start_date: null,
  client: null,
  slots: [{ id: SLOT, label: "React developer", skill: "React", skill_id: "s-react", count: 1 }],
  milestones: [],
  schedule: null,
};
const SLOT_API = "1c8e5d2f-3a4b-4c5d-9e0f-1a2b3c4d5e6f";
const PLAN_DAYS = 15;
const M1 = "m-design";
const M2 = "m-build";
const PLANNED_DETAIL = {
  ...DETAIL,
  client: { name: "Dhaka Bites Ltd" },
  // The API slot comes first from the server; my skill (React) should still be listed first.
  slots: [
    { id: SLOT_API, label: "", skill: "FastAPI", skill_id: "s-fastapi", count: 1 },
    ...DETAIL.slots,
  ],
  milestones: [
    { id: M1, name: "Design", duration_days: 5, status: "PLANNED" },
    { id: M2, name: "Build", duration_days: 10, status: "PLANNED" },
  ],
  schedule: {
    // A named constant: the motion-lint rule forbids numeric `duration:` literals.
    duration: PLAN_DAYS,
    nodes: [
      { key: M1, name: "Design", es: 0, ef: 5, ls: 0, lf: 5, slack: 0, critical: true },
      { key: M2, name: "Build", es: 5, ef: 15, ls: 5, lf: 15, slack: 0, critical: true },
    ],
    edges: [{ predecessor: M1, successor: M2 }],
  },
};
/** A developer profile listing React (only `skills` matters here). */
const PROFILE = {
  headline: "",
  bio: "",
  hours_per_week: 40,
  skills: [{ skill_id: "s-react", name: "React", domain: "FRONTEND", self_level: 4 }],
};

beforeEach(() => {
  server.use(http.get(`${API}/me/developer-profile`, () => HttpResponse.json(PROFILE)));
});

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
        HttpResponse.json([
          {
            project: CARD,
            skill_match_count: 2,
            matched_skills: ["FastAPI", "React"],
            typical_days: null,
          },
        ]),
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
      http.get(`${API}/projects/search`, () => HttpResponse.json({ items: [], next_cursor: null })),
    );
    const { router } = routes("/dev/find", <FindProjectsPage />, "/dev/find");
    await user.type(await screen.findByLabelText("Search projects"), "ordering");
    await waitFor(() => {
      expect(router.state.location.search).toContain("q=ordering");
    });
    expect(await screen.findByText("No projects match")).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    server.use(
      http.get(`${API}/skills`, () => HttpResponse.json(SKILLS)),
      http.get(`${API}/projects/recommended`, () => HttpResponse.json([])),
      http.get(`${API}/projects/search`, () => HttpResponse.json({ items: [], next_cursor: null })),
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
      http.get(`${API}/me/portfolio`, () => HttpResponse.json([])),
    );
  }

  it("says bidding has closed after the deadline and offers no form", async () => {
    base();
    server.use(
      http.get(`${API}/public/projects/${PID}`, () =>
        HttpResponse.json({
          ...DETAIL,
          open_for_bids: false,
          bidding_deadline: "2026-10-20T06:00:00Z",
        }),
      ),
    );
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);
    expect(await screen.findByText("Bidding has closed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Place sealed bid/ })).not.toBeInTheDocument();
  });

  it("sends hours, contribution and at most three of my portfolio items", async () => {
    const user = userEvent.setup();
    base();
    let posted: Record<string, unknown> | null = null;
    const items = ["Kitchen app", "Shop site", "Clinic queue", "Bus tracker"].map((title, i) => ({
      id: `p${String(i)}`,
      title,
    }));
    server.use(
      http.get(`${API}/me/portfolio`, () => HttpResponse.json(items)),
      http.post(`${API}/projects/${PID}/bids/eligibility`, () =>
        HttpResponse.json({
          eligible: true,
          reason: null,
          message: "You meet every requirement.",
          checks: [],
        }),
      ),
      http.post(`${API}/projects/${PID}/bids`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: "b1", status: "ACTIVE" });
      }),
    );
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);
    await user.click(await screen.findByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: /React/ }));
    await user.type(screen.getByLabelText(/Your price/), "18000");
    await user.type(screen.getByLabelText(/Days you need/), "20");
    await user.type(screen.getByLabelText("Hours a week"), "15");
    await user.type(screen.getByLabelText("Expected contribution"), "Front end");
    for (const title of ["Kitchen app", "Shop site", "Clinic queue"]) {
      await user.click(await screen.findByRole("checkbox", { name: title }));
    }
    expect(screen.getByRole("checkbox", { name: "Bus tracker" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Place sealed bid/ }));
    await waitFor(() => {
      expect(posted).toMatchObject({
        hours_per_week_committed: 15,
        expected_contribution: "Front end",
        portfolio_item_ids: ["p0", "p1", "p2"],
      });
    });
  });

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
    expect(
      await screen.findByText(/would be filtered out/i, {}, { timeout: 3000 }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Place sealed bid/ }));
    await waitFor(() => {
      expect(posted).toMatchObject({ slot_id: SLOT, days_needed: 31, price_paisa: 2_000_000 });
    });
  });

  it("shows an existing bid with a withdraw action", async () => {
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.get(`${API}/public/projects/${PID}`, () => HttpResponse.json(DETAIL)),
      http.get(`${API}/me/portfolio`, () => HttpResponse.json([])),
      http.get(`${API}/me/bids`, () =>
        HttpResponse.json([
          {
            id: "b1",
            project_id: PID,
            slot_id: SLOT,
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
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);
    expect(await screen.findByText("Your bid")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Withdraw bid/ })).toBeInTheDocument();
  });

  it("edits an existing bid with the form filled in from it", async () => {
    const user = userEvent.setup();
    let patched: unknown = null;
    const bid = {
      id: "b1",
      project_id: PID,
      slot_id: SLOT,
      status: "ACTIVE",
      price_paisa: 1_800_000,
      days_needed: 20,
      proposal: "React and tests.",
      expected_contribution: "Front end",
      portfolio_item_ids: [],
      hours_per_week_committed: 25,
      created_at: "2026-10-21T06:00:00Z",
      updated_at: "2026-10-21T06:00:00Z",
    };
    base();
    server.use(
      http.get(`${API}/me/bids`, () => HttpResponse.json([bid])),
      http.post(`${API}/projects/${PID}/bids/eligibility`, () =>
        HttpResponse.json({
          eligible: true,
          reason: null,
          message: "You meet every requirement.",
          checks: [],
        }),
      ),
      http.patch(`${API}/bids/b1`, async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json({ ...bid, price_paisa: 1_500_000 });
      }),
    );
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);
    await user.click(await screen.findByRole("button", { name: "Edit bid" }));
    expect(screen.getByText("Edit your bid")).toBeInTheDocument();
    const price = screen.getByLabelText("Your price (৳)");
    expect(price).toHaveValue(18_000);
    expect(screen.getByLabelText("Days you need")).toHaveValue(20);
    expect(screen.getByLabelText("Hours a week")).toHaveValue(25);
    await user.clear(price);
    await user.type(price, "15000");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(patched).toMatchObject({
        slot_id: SLOT,
        price_paisa: 1_500_000,
        days_needed: 20,
        hours_per_week_committed: 25,
        proposal: "React and tests.",
        expected_contribution: "Front end",
      });
    });
  });

  it("doesn't offer an empty bid form while my bids are loading or failed", async () => {
    base();
    server.use(
      http.get(`${API}/me/bids`, () =>
        HttpResponse.json({ error: { code: "INTERNAL_ERROR" } }, { status: 500 }),
      ),
    );
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);
    expect(await screen.findByText("We couldn’t check whether you’ve bid")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Place sealed bid/ })).not.toBeInTheDocument();
  });

  it("checks price, days and hours with the server's limits", async () => {
    const user = userEvent.setup();
    base();
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);
    await user.type(await screen.findByLabelText("Days you need"), "1.5");
    expect(
      await screen.findByText("Use a whole number of days from 1 to 365."),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Hours a week"), "200");
    expect(screen.getByText("Use a whole number of hours from 1 to 168.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your price (৳)"), "0.004");
    expect(screen.getByText("Use an amount from ৳0.01 to ৳100,000,000.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Place sealed bid/ })).toBeDisabled();
  });

  it("leaves out a deleted portfolio item when a bid is edited", async () => {
    const user = userEvent.setup();
    let patched: Record<string, unknown> | null = null;
    const bid = {
      id: "b1",
      project_id: PID,
      slot_id: SLOT,
      status: "ACTIVE",
      price_paisa: 1_800_000,
      days_needed: 20,
      proposal: "",
      expected_contribution: "",
      portfolio_item_ids: ["kept", "deleted"],
      hours_per_week_committed: 20,
      created_at: "2026-10-21T06:00:00Z",
      updated_at: "2026-10-21T06:00:00Z",
    };
    base();
    server.use(
      http.get(`${API}/me/bids`, () => HttpResponse.json([bid])),
      http.get(`${API}/me/portfolio`, () =>
        HttpResponse.json([
          {
            id: "kept",
            title: "Shop",
            description: "",
            url: null,
            skill_ids: [],
            position: 0,
            images: [],
          },
        ]),
      ),
      http.patch(`${API}/bids/b1`, async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(bid);
      }),
    );
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);
    await user.click(await screen.findByRole("button", { name: "Edit bid" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(patched?.portfolio_item_ids).toEqual(["kept"]);
    });
  });
});

describe("Find Projects filters", () => {
  function searchCapturing(seen: URL[], items: unknown[] = []) {
    server.use(
      http.get(`${API}/skills`, () =>
        HttpResponse.json([...SKILLS, { id: "s-fastapi", name: "FastAPI", domain: "BACKEND" }]),
      ),
      http.get(`${API}/projects/recommended`, () => HttpResponse.json([])),
      http.get(`${API}/projects/search`, ({ request }) => {
        seen.push(new URL(request.url));
        return HttpResponse.json({ items, next_cursor: null });
      }),
    );
  }
  const last = (seen: URL[]) => seen[seen.length - 1]?.searchParams ?? new URLSearchParams();

  it("sends every filter in the URL to the search (budget in paisa)", async () => {
    const seen: URL[] = [];
    searchCapturing(seen);
    routes(
      "/dev/find",
      <FindProjectsPage />,
      "/dev/find?budget_min=1000&budget_max=5000&deadline_max=30&role=React&team_size=4&hours=10&skills=FastAPI",
    );
    await waitFor(() => {
      expect(seen.length).toBeGreaterThan(0);
    });
    const q = last(seen);
    expect(q.get("budget_min")).toBe("100000");
    expect(q.get("budget_max")).toBe("500000");
    expect(q.get("deadline_max")).toBe("30");
    expect(q.get("role")).toBe("React");
    expect(q.get("team_size")).toBe("4");
    expect(q.get("hours")).toBe("10");
    expect(q.getAll("skills")).toEqual(["FastAPI"]);
    // The panel shows them back.
    expect(screen.getByLabelText("Minimum")).toHaveValue(1000);
    expect(screen.getByLabelText("Hours a week you can give")).toHaveValue(10);
  });

  it("shows invalid values as field errors and leaves them out of the search", async () => {
    const seen: URL[] = [];
    searchCapturing(seen);
    routes(
      "/dev/find",
      <FindProjectsPage />,
      "/dev/find?budget_min=5000&budget_max=1000&hours=200&team_size=1&deadline_max=0",
    );
    expect(await screen.findByText("Use a maximum at or above the minimum.")).toBeInTheDocument();
    expect(screen.getByText("Use a whole number of hours from 1 to 168.")).toBeInTheDocument();
    expect(screen.getByText("Use a whole number of days from 1 to 365.")).toBeInTheDocument();
    expect(screen.getByText("Choose a team size from 2 to 10.")).toBeInTheDocument();
    await waitFor(() => {
      expect(seen.length).toBeGreaterThan(0);
    });
    const q = last(seen);
    expect(q.get("budget_min")).toBe("500000");
    for (const key of ["budget_max", "hours", "team_size", "deadline_max"]) {
      expect(q.has(key)).toBe(false);
    }
  });

  it("puts typed filters in the URL and clears them, keeping the sort", async () => {
    const user = userEvent.setup();
    const seen: URL[] = [];
    searchCapturing(seen);
    const { router } = routes("/dev/find", <FindProjectsPage />, "/dev/find?sort=budget");
    await user.type(await screen.findByLabelText("Hours a week you can give"), "15");
    await waitFor(() => {
      expect(router.state.location.search).toContain("hours=15");
    });
    await waitFor(() => {
      expect(last(seen).get("hours")).toBe("15");
    });
    // Empty results with filters on: suggest broadening, with a way to clear.
    expect(await screen.findByText(/Try fewer skills, a wider budget/)).toBeInTheDocument();
    const clear = screen.getAllByRole("button", { name: "Clear filters" });
    expect(clear.length).toBeGreaterThan(0);
    await user.click(clear[0] as HTMLElement);
    await waitFor(() => {
      expect(router.state.location.search).toBe("?sort=budget");
    });
    expect(screen.queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();
  });

  it("offers no clear button and a plain empty state without filters", async () => {
    searchCapturing([]);
    routes("/dev/find", <FindProjectsPage />, "/dev/find");
    expect(await screen.findByText(/No open projects right now/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();
  });

  it("highlights the skills on my profile in result cards", async () => {
    searchCapturing([], [CARD]);
    routes("/dev/find", <FindProjectsPage />, "/dev/find");
    expect(await screen.findByText("1 of your skills")).toBeInTheDocument();
    const chips = screen.getByRole("list", { name: "Skills needed" }).querySelectorAll("li");
    // React (mine) comes first and says so; FastAPI doesn't.
    expect(chips[0]).toHaveTextContent("React (your skill)");
    expect(chips[1]).toHaveTextContent(/^FastAPI$/);
  });

  it("doesn't highlight anything when my profile fails to load", async () => {
    server.use(
      http.get(`${API}/me/developer-profile`, () =>
        HttpResponse.json({ error: { code: "INTERNAL_ERROR" } }, { status: 500 }),
      ),
    );
    searchCapturing([], [CARD]);
    routes("/dev/find", <FindProjectsPage />, "/dev/find");
    expect(await screen.findByText("Online ordering system")).toBeInTheDocument();
    expect(screen.queryByText(/your skill/)).not.toBeInTheDocument();
  });
});

describe("Project details", () => {
  function details(body: JsonBodyType) {
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.get(`${API}/public/projects/${PID}`, () => HttpResponse.json(body)),
      http.get(`${API}/me/bids`, () => HttpResponse.json([])),
      http.get(`${API}/me/portfolio`, () => HttpResponse.json([])),
    );
  }

  it("shows the client, description, milestones and a mini Gantt", async () => {
    details(PLANNED_DETAIL);
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);
    expect(await screen.findByText("Dhaka Bites Ltd")).toBeInTheDocument();
    expect(screen.getByText("Client")).toBeInTheDocument();
    expect(screen.getByText(DETAIL.description)).toBeInTheDocument();
    expect(screen.getByText("4 people")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Milestones" });
    expect(list).toHaveTextContent("Design");
    expect(list).toHaveTextContent("Build");
    expect(screen.getAllByText("Planned")).toHaveLength(2);
    expect(screen.getByRole("img")).toHaveAccessibleName(/2 milestones/i);
    expect(screen.getByLabelText(/Design: days 0–5, on the critical path/)).toBeInTheDocument();
    expect(screen.getByText("Highlighted roles match skills on your profile.")).toBeInTheDocument();
  });

  it("leaves out the client for guests and says when there's no plan", async () => {
    details(DETAIL);
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);
    expect(await screen.findByText("No plan shared yet")).toBeInTheDocument();
    expect(screen.queryByText("Client")).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("lists my skills' roles first and marks the others", async () => {
    const user = userEvent.setup();
    details(PLANNED_DETAIL);
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);
    await screen.findByText("Dhaka Bites Ltd");
    await waitFor(() => {
      expect(
        screen.getByText("Highlighted roles match skills on your profile."),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("combobox"));
    const options = await screen.findAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([
      "React: React developer",
      "FastAPI (not one of your skills)",
    ]);
    await user.click(options[1] as HTMLElement);
    expect(await screen.findByText("Not one of your skills")).toBeInTheDocument();
    expect(
      screen.getByText(/This role needs FastAPI, which isn’t on your profile/),
    ).toBeInTheDocument();
  });

  it("marks nothing while my skills are unknown", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${API}/me/developer-profile`, () =>
        HttpResponse.json({ error: { code: "INTERNAL_ERROR" } }, { status: 500 }),
      ),
    );
    details(PLANNED_DETAIL);
    routes("/dev/projects/:id", <ProjectBidPage />, `/dev/projects/${PID}`);
    await screen.findByText("Dhaka Bites Ltd");
    await user.click(screen.getByRole("combobox"));
    const options = await screen.findAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["FastAPI", "React: React developer"]);
  });
});
