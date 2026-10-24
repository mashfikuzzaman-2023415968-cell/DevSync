/** Projects feature: CPM charts, the create-project wizard, the plan and list pages (Phase 4). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, type JsonBodyType } from "msw";
import { useState, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { CpmNode, Skill } from "@/api/types";
import { CpmTable } from "@/components/CpmTable";
import { DependencyGraph, nameLines } from "@/components/DependencyGraph";
import { Gantt } from "@/components/Gantt";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import * as hooks from "./api";
import CreateProjectPage from "./CreateProjectPage";
import { MilestonesStep } from "./MilestonesStep";
import MyProjectsPage from "./MyProjectsPage";
import PlanPage from "./PlanPage";
import { TagPicker } from "./TagPicker";
import { budgetSchema, infoSchema, newKey, toPaisa, toTaka, type MilestoneRow } from "./schemas";

const API = "https://testserver/api/v1";

// Six-milestone golden from spec §18.2: duration 24, Frontend has slack 4.
const NODES: CpmNode[] = [
  { key: "a", name: "Requirements", es: 0, ef: 4, ls: 0, lf: 4, slack: 0, critical: true },
  { key: "b", name: "Database", es: 4, ef: 9, ls: 4, lf: 9, slack: 0, critical: true },
  { key: "c", name: "Backend API", es: 9, ef: 17, ls: 9, lf: 17, slack: 0, critical: true },
  { key: "d", name: "Frontend", es: 4, ef: 13, ls: 8, lf: 17, slack: 4, critical: false },
  { key: "e", name: "Integration", es: 17, ef: 20, ls: 17, lf: 20, slack: 0, critical: true },
  { key: "f", name: "Testing", es: 20, ef: 24, ls: 20, lf: 24, slack: 0, critical: true },
];
const EDGES: [string, string][] = [
  ["a", "b"],
  ["b", "c"],
  ["a", "d"],
  ["c", "e"],
  ["d", "e"],
  ["e", "f"],
];

const ME = {
  id: "c1",
  email: "rahim@example.com",
  phone_e164: "+8801712345678",
  display_name: "Rahim",
  role: "CLIENT",
  status: "ACTIVE",
  email_verified: true,
  phone_verified: true,
  totp_enabled: false,
  totp_verified: false,
  payment_verified: false,
  created_at: "2026-10-17T00:00:00Z",
};

const SKILLS: Skill[] = [
  { id: "s-react", name: "React", domain: "FRONTEND" },
  { id: "s-api", name: "FastAPI", domain: "BACKEND" },
];

// CPM "duration" values live in named constants so the motion-lint rule (which forbids numeric
// `duration:` literals) doesn't mistake schedule data for an animation timing.
const DURATION_24 = 24;
const DURATION_40 = 40;
const NO_DURATION = 0;

describe("schemas", () => {
  it("converts taka and paisa", () => {
    expect(toPaisa(125)).toBe(12_500);
    expect(toTaka(12_500)).toBe(125);
    expect(toPaisa(0.5)).toBe(50);
  });

  it("rejects short titles and accepts valid ones", () => {
    expect(infoSchema.safeParse({ title: "no", summary: "" }).success).toBe(false);
    expect(infoSchema.safeParse({ title: "Ordering system", summary: "x" }).success).toBe(true);
  });

  it("requires a positive budget", () => {
    expect(
      budgetSchema.safeParse({ budget_taka: 0, bonus_taka: 0, bidding_deadline: "" }).success,
    ).toBe(false);
    expect(
      budgetSchema.safeParse({ budget_taka: 1000, bonus_taka: 0, bidding_deadline: "" }).success,
    ).toBe(true);
  });

  it("mints unique keys", () => {
    expect(newKey()).not.toBe(newKey());
  });
});

describe("Gantt", () => {
  it("labels the chart and marks critical milestones", () => {
    render(<Gantt nodes={NODES} today={10} deadlineDays={30} />);
    const img = screen.getByRole("img");
    expect(img).toHaveAccessibleName(/6 milestones/i);
    // Every milestone bar is a focusable group with a descriptive label.
    expect(
      screen.getByLabelText(/Requirements: days 0–4, on the critical path/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Frontend: days 4–13, slack 4 days/i)).toBeInTheDocument();
  });

  it("renders without a today or deadline line and counts days without a start date", () => {
    const { container } = render(<Gantt nodes={NODES} />);
    expect(screen.getByRole("img")).toHaveAccessibleName(/24 days/i);
    expect(screen.getByText("Days from start")).toBeInTheDocument();
    expect(screen.queryByText("Today")).not.toBeInTheDocument();
    expect(screen.queryByText("Deadline")).not.toBeInTheDocument();
    expect(container.querySelector("line.stroke-warning")).toBeNull();
    expect(container.querySelector("line.stroke-primary")).toBeNull();
  });

  it("shows the deadline and today lines with legend entries", () => {
    const { container } = render(<Gantt nodes={NODES} today={10} deadlineDays={30} />);
    expect(screen.getByText("Deadline")).toBeInTheDocument();
    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(container.querySelector("line.stroke-warning")).not.toBeNull();
    expect(container.querySelector("line.stroke-primary")).not.toBeNull();
  });

  it("hides a today line that falls outside the plan", () => {
    const { container } = render(<Gantt nodes={NODES} today={-3} />);
    expect(screen.queryByText("Today")).not.toBeInTheDocument();
    expect(container.querySelector("line.stroke-primary")).toBeNull();
    render(<Gantt nodes={NODES} today={99} />);
    expect(screen.queryByText("Today")).not.toBeInTheDocument();
  });

  it("puts real dates on the axis and in the bar labels when the start date is known", () => {
    render(<Gantt nodes={NODES} startDate="2026-11-02" />);
    expect(screen.getByText("Nov 2026")).toBeInTheDocument();
    // Frontend runs offsets [4, 13): 6 Nov to 14 Nov inclusive.
    expect(
      screen.getByLabelText("Frontend: days 4–13, slack 4 days, 6 Nov 2026 – 14 Nov 2026"),
    ).toBeInTheDocument();
  });

  it("starts a new month label when the plan crosses into the next month", () => {
    render(<Gantt nodes={NODES} startDate="2026-11-20" />);
    expect(screen.getByText("Nov 2026")).toBeInTheDocument();
    expect(screen.getByText("Dec 2026")).toBeInTheDocument();
  });

  it("draws one arrow per known dependency and ignores unknown keys", () => {
    const { container } = render(
      <Gantt nodes={NODES} edges={[...EDGES, ["a", "missing"], ["ghost", "b"]]} />,
    );
    expect(container.querySelectorAll("path[marker-end]")).toHaveLength(EDGES.length);
    // Critical links (critical → critical, back to back) use the rose arrow.
    expect(container.querySelectorAll("path.stroke-danger[marker-end]")).toHaveLength(4);
  });

  it("explains a milestone when its bar is focused", async () => {
    const user = userEvent.setup();
    render(<Gantt nodes={NODES} edges={EDGES} startDate="2026-11-02" />);
    expect(screen.getByText(/Hover, focus or tap a bar/)).toBeInTheDocument();
    await user.tab(); // the zoom control (one tab stop)
    await user.tab(); // the first bar
    expect(document.activeElement).toHaveAccessibleName(/^Requirements: days 0–4/);
    const details = screen.getByText((_, el) => el?.tagName === "FIGCAPTION");
    expect(details).toHaveTextContent(
      "Requirements: 2 Nov 2026 – 5 Nov 2026 (4 days). On the critical path",
    );
    await user.click(screen.getByLabelText(/^Frontend: days 4–13/));
    expect(details).toHaveTextContent("Can slip 4 days without delaying the finish.");
    expect(details).toHaveTextContent("Starts after Requirements.");
  });

  it("keeps long names whole instead of cutting them off", () => {
    const long = "Payment gateway integration and reconciliation reports";
    const node: CpmNode = {
      key: "x",
      name: long,
      es: 0,
      ef: 4,
      ls: 0,
      lf: 4,
      slack: 0,
      critical: true,
    };
    render(<Gantt nodes={[node]} />);
    expect(screen.getByTitle(long)).toHaveTextContent(long);
  });

  it("switches between day and week zoom", async () => {
    const user = userEvent.setup();
    render(<Gantt nodes={NODES} />);
    expect(screen.getByRole("radio", { name: "Days" })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: "Weeks" }));
    expect(screen.getByText("Week 1")).toBeInTheDocument();
    expect(screen.getByText("Week 4")).toBeInTheDocument();
  });

  it("starts long plans zoomed out to weeks", () => {
    render(<Gantt nodes={NODES} deadlineDays={120} />);
    expect(screen.getByRole("radio", { name: "Weeks" })).toBeChecked();
  });
});

describe("DependencyGraph", () => {
  it("renders one label per milestone and names the critical path", () => {
    render(
      <DependencyGraph
        nodes={NODES.map((n) => ({ key: n.key, name: n.name, critical: n.critical }))}
        edges={EDGES}
      />,
    );
    expect(screen.getByRole("img")).toHaveAccessibleName(/critical path/i);
    expect(screen.getByText("Requirements", { selector: "tspan" })).toBeInTheDocument();
    expect(screen.getByText("Testing", { selector: "tspan" })).toBeInTheDocument();
  });

  it("makes every milestone a keyboard stop so a wide graph can be scrolled", async () => {
    const user = userEvent.setup();
    render(
      <DependencyGraph
        nodes={NODES.map((n) => ({ key: n.key, name: n.name, critical: n.critical }))}
        edges={EDGES}
      />,
    );
    await user.tab();
    expect(document.activeElement).toHaveAccessibleName("Requirements, on the critical path");
    expect(screen.getByLabelText("Frontend")).toHaveAttribute("tabindex", "0");
  });

  it("wraps long names onto two lines and keeps the full name as a title", () => {
    const long = "Payment gateway integration and reconciliation";
    const { container } = render(
      <DependencyGraph nodes={[{ key: "p", name: long, critical: false }]} edges={[]} />,
    );
    expect(container.querySelector("title + text")?.textContent).toBe(
      "Payment gatewayintegration and…",
    );
    expect(container.querySelectorAll("tspan")).toHaveLength(2);
    expect(within(container).getByText(long, { selector: "title" })).toBeInTheDocument();
  });
});

describe("nameLines", () => {
  it("keeps short names on one line", () => {
    expect(nameLines("Database")).toEqual(["Database"]);
    expect(nameLines("  Testing   & launch ")).toEqual(["Testing & launch"]);
  });

  it("splits at spaces and fills each line up to the limit", () => {
    expect(nameLines("Requirements & design")).toEqual(["Requirements &", "design"]);
    expect(nameLines("12345 67890", 11)).toEqual(["12345 67890"]);
    expect(nameLines("12345 678901", 11)).toEqual(["12345", "678901"]);
  });

  it("breaks a word longer than a line and elides only past two lines", () => {
    expect(nameLines("Internationalisation", 10)).toEqual(["Internatio", "nalisation"]);
    expect(nameLines("aaaa bbbb cccc dddd", 9)).toEqual(["aaaa bbbb", "cccc dddd"]);
    expect(nameLines("aaaa bbbb cccc dddd eeee", 9)).toEqual(["aaaa bbbb", "cccc ddd…"]);
  });
});

describe("CpmTable", () => {
  it("shows slack and a critical badge", () => {
    render(<CpmTable nodes={NODES} />);
    const row = screen.getByRole("row", { name: /Frontend/ });
    expect(within(row).getByText("4 days")).toBeInTheDocument();
    const critical = screen.getByRole("row", { name: /Requirements/ });
    expect(within(critical).getByText("Critical")).toBeInTheDocument();
  });
});

describe("TagPicker", () => {
  it("toggles options and reports changes", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { rerender } = render(
      <TagPicker options={[{ value: "a", label: "Alpha" }]} value={[]} onChange={onChange} />,
    );
    await user.click(screen.getByRole("button", { name: "Alpha" }));
    expect(onChange).toHaveBeenCalledWith(["a"]);
    rerender(
      <TagPicker options={[{ value: "a", label: "Alpha" }]} value={["a"]} onChange={onChange} />,
    );
    expect(screen.getByRole("button", { name: "Alpha" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows the empty hint when there are no options", () => {
    render(<TagPicker options={[]} value={[]} onChange={vi.fn()} empty="Nothing here." />);
    expect(screen.getByText("Nothing here.")).toBeInTheDocument();
  });
});

function routes(path: string, element: React.ReactNode) {
  return [
    { path, element },
    { path: "*", element: <Probe label="elsewhere" /> },
  ];
}

/** A cursor page of My projects (spec §10.1). */
function page(items: JsonBodyType[], next_cursor: string | null = null) {
  return { items, next_cursor };
}

describe("MyProjectsPage", () => {
  it("loads older projects with Load more, passing the cursor", async () => {
    const user = userEvent.setup();
    const asked: string[] = [];
    const row = (id: string, title: string) => ({
      id,
      title,
      status: "BIDDING",
      budget_paisa: 0,
      team_size: 2,
      deadline_days: 30,
      bidding_deadline: null,
      updated_at: "2026-10-19T06:00:00Z",
    });
    server.use(
      http.get(`${API}/projects`, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        asked.push(cursor ?? "-");
        return HttpResponse.json(
          cursor === "c2" ? page([row("p2", "Older project")]) : page([row("p1", "Newest")], "c2"),
        );
      }),
    );
    renderRoutes(routes("/client/projects", <MyProjectsPage />), "/client/projects");
    expect(await screen.findByRole("link", { name: "Newest" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Older project" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("link", { name: "Older project" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Newest" })).toBeInTheDocument();
    expect(asked).toEqual(["-", "c2"]);
    // The last page has no cursor: no more Load more.
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("shows the empty state when there are no projects", async () => {
    server.use(http.get(`${API}/projects`, () => HttpResponse.json(page([]))));
    renderRoutes(routes("/client/projects", <MyProjectsPage />), "/client/projects");
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
  });

  it("shows an error state and retries", async () => {
    const user = userEvent.setup();
    let hits = 0;
    server.use(
      http.get(`${API}/projects`, () => {
        hits += 1;
        return hits === 1
          ? HttpResponse.json({ error: { code: "INTERNAL_ERROR" } }, { status: 500 })
          : HttpResponse.json(page([]));
      }),
    );
    renderRoutes(routes("/client/projects", <MyProjectsPage />), "/client/projects");
    await user.click(await screen.findByRole("button", { name: /Try again/i }));
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
  });

  it("lets the client continue a draft and view the plan of a published project", async () => {
    const row = (id: string, title: string, status: string) => ({
      id,
      title,
      status,
      budget_paisa: 0,
      team_size: 2,
      deadline_days: 30,
      bidding_deadline: null,
      updated_at: "2026-10-19T06:00:00Z",
    });
    server.use(
      http.get(`${API}/projects`, () =>
        HttpResponse.json(
          page([row("d1", "Half-planned app", "DRAFT"), row("b1", "Ordering", "BIDDING")]),
        ),
      ),
    );
    renderRoutes(routes("/client/projects", <MyProjectsPage />), "/client/projects");
    const cont = await screen.findByRole("link", { name: "Continue editing" });
    expect(cont).toHaveAttribute("href", "/client/projects/new?draft=d1");
    expect(screen.getByRole("link", { name: "Half-planned app" })).toHaveAttribute(
      "href",
      "/client/projects/new?draft=d1",
    );
    expect(screen.getAllByRole("link", { name: "View plan" })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "View plan" })).toHaveAttribute(
      "href",
      "/client/projects/b1/plan",
    );
  });

  it("lists projects and cancels one with a reason and the typed title", async () => {
    const user = userEvent.setup();
    let cancelled: unknown = null;
    server.use(
      http.get(`${API}/projects`, () =>
        HttpResponse.json(
          page([
            {
              id: "p1",
              title: "Ordering system",
              status: "BIDDING",
              budget_paisa: 12_000_000,
              team_size: 3,
              deadline_days: 30,
              bidding_deadline: "2026-11-01T00:00:00Z",
              updated_at: "2026-10-18T00:00:00Z",
            },
            {
              id: "p2",
              title: "Legacy migration",
              status: "COMPLETED",
              budget_paisa: 5_000_000,
              team_size: 2,
              deadline_days: 14,
              bidding_deadline: null,
              updated_at: "2026-09-01T00:00:00Z",
            },
          ]),
        ),
      ),
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.post(`${API}/projects/p1/cancel`, async ({ request }) => {
        cancelled = await request.json();
        return HttpResponse.json({ id: "p1", status: "CANCELLED" });
      }),
    );
    renderRoutes(routes("/client/projects", <MyProjectsPage />), "/client/projects");

    expect(await screen.findByText("Ordering system")).toBeInTheDocument();
    expect(screen.getByText(/Bidding/)).toBeInTheDocument();
    // A completed project shows its status but offers no Cancel action.
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText(/bids close/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Cancel" })).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    const dialog = await screen.findByRole("alertdialog").catch(() => screen.getByRole("dialog"));
    const reason = within(dialog).getByLabelText("Reason");
    // Too short: the confirm stays disabled.
    expect(within(dialog).getByRole("button", { name: "Cancel project" })).toBeDisabled();
    await user.type(reason, "Re-scoping the work.");
    // A reason alone isn't enough: the project title must be typed to confirm.
    const confirm = within(dialog).getByRole("button", { name: "Cancel project" });
    expect(confirm).toBeDisabled();
    const typed = within(dialog).getByLabelText(/Type “Ordering system” to confirm/);
    await user.type(typed, "Ordering");
    expect(confirm).toBeDisabled();
    await user.type(typed, " system");
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    await waitFor(() => {
      expect(cancelled).toEqual({ reason: "Re-scoping the work." });
    });
  });
});

describe("PlanPage", () => {
  const plan = {
    baseline_version: 1,
    critical_paths: [["Requirements", "Database", "Backend API", "Integration", "Testing"]],
    deadline_days: 30,
    duration: DURATION_24,
    exceeds_deadline: false,
    nodes: NODES,
    edges: EDGES.map(([p, s]) => ({ predecessor: p, successor: s })),
  };

  function planHandlers(status = "BIDDING") {
    server.use(
      http.get(`${API}/projects/p1`, () =>
        HttpResponse.json({
          id: "p1",
          title: "Ordering system",
          status,
          start_date: "2026-11-01T00:00:00Z",
          deadline_days: 30,
          version: 1,
          client_id: "c1",
          budget_paisa: 0,
          bonus_pool_paisa: 0,
          team_size: 3,
          summary: "",
          description: "",
          requirements: "",
          bidding_deadline: null,
          bidding_extensions: 0,
          cancel_reason: null,
          current_baseline_id: null,
          created_at: "2026-10-01T00:00:00Z",
          updated_at: "2026-10-01T00:00:00Z",
        }),
      ),
    );
  }

  it("renders the schedule and switches to the table", async () => {
    const user = userEvent.setup();
    planHandlers();
    server.use(http.get(`${API}/projects/p1/plan`, () => HttpResponse.json(plan)));
    renderRoutes(routes("/client/projects/:id/plan", <PlanPage />), "/client/projects/p1/plan");

    expect(await screen.findByText("Plan: Ordering system")).toBeInTheDocument();
    expect(screen.getByText("Duration 24 days")).toBeInTheDocument();
    expect(screen.getByText("5 critical milestones")).toBeInTheDocument();
    // The dependency graph draws one arrow per edge from the plan response.
    const graph = screen.getByRole("img", { name: /depend/i });
    expect(graph.querySelectorAll("path")).toHaveLength(EDGES.length);
    // The Gantt draws the same dependencies, real dates and no today line before work starts.
    const gantt = screen.getByRole("img", { name: /Gantt chart/i });
    expect(gantt.querySelectorAll("path[marker-end]")).toHaveLength(EDGES.length);
    expect(screen.getByText("Nov 2026")).toBeInTheDocument();
    expect(screen.queryByText("Today")).not.toBeInTheDocument();
    // Toggle to the table alternative.
    await user.click(screen.getByRole("radio", { name: "Table" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("gives the last working day as the finish date, like the Gantt", async () => {
    planHandlers(); // starts 1 Nov; the plan takes 24 days (offsets 0–24)
    server.use(http.get(`${API}/projects/p1/plan`, () => HttpResponse.json(plan)));
    renderRoutes(routes("/client/projects/:id/plan", <PlanPage />), "/client/projects/p1/plan");
    expect(await screen.findByText("Finish 24 Nov 2026")).toBeInTheDocument();
  });

  it("says “1 critical milestone” in the singular", async () => {
    planHandlers();
    const one = { ...plan, nodes: [NODES[0]], edges: [] };
    server.use(http.get(`${API}/projects/p1/plan`, () => HttpResponse.json(one)));
    renderRoutes(routes("/client/projects/:id/plan", <PlanPage />), "/client/projects/p1/plan");
    expect(await screen.findByText("1 critical milestone")).toBeInTheDocument();
  });

  it("marks today on the Gantt once work is under way", async () => {
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-11-11T06:00:00Z"));
    planHandlers("IN_PROGRESS");
    server.use(http.get(`${API}/projects/p1/plan`, () => HttpResponse.json(plan)));
    renderRoutes(routes("/client/projects/:id/plan", <PlanPage />), "/client/projects/p1/plan");
    expect(await screen.findByText("Today")).toBeInTheDocument();
    vi.restoreAllMocks();
  });

  it("shows the empty state when the project has no milestones", async () => {
    planHandlers();
    server.use(
      http.get(`${API}/projects/p1/plan`, () =>
        HttpResponse.json({
          baseline_version: null,
          critical_paths: [],
          deadline_days: 30,
          duration: NO_DURATION,
          exceeds_deadline: false,
          nodes: [],
        }),
      ),
    );
    renderRoutes(routes("/client/projects/:id/plan", <PlanPage />), "/client/projects/p1/plan");
    expect(await screen.findByText("No plan yet")).toBeInTheDocument();
  });

  it("shows an error state with a retry", async () => {
    planHandlers();
    server.use(
      http.get(`${API}/projects/p1/plan`, () =>
        HttpResponse.json({ error: { code: "NOT_FOUND", message: "no" } }, { status: 404 }),
      ),
    );
    renderRoutes(routes("/client/projects/:id/plan", <PlanPage />), "/client/projects/p1/plan");
    expect(await screen.findByText(/couldn’t load this plan/i)).toBeInTheDocument();
  });
});

describe("CreateProjectPage", () => {
  it("creates a draft and walks through the first steps", async () => {
    const user = userEvent.setup();
    let created: unknown = null;
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.get(`${API}/skills`, () => HttpResponse.json(SKILLS)),
      http.post(`${API}/projects`, async ({ request }) => {
        created = await request.json();
        return HttpResponse.json({ id: "p1", version: 1, status: "DRAFT" });
      }),
      http.patch(`${API}/projects/p1`, () => HttpResponse.json({ id: "p1", version: 2 })),
    );
    renderRoutes(
      [
        ...routes("/client/projects/new", <CreateProjectPage />),
        { path: "/client/projects/:id/plan", element: <Probe label="plan" /> },
      ],
      "/client/projects/new",
    );

    expect(await screen.findByText("Create a project")).toBeInTheDocument();
    // Continue is disabled until the title is long enough.
    const continueBtn = screen.getByRole("button", { name: /Continue/ });
    expect(continueBtn).toBeDisabled();
    await user.type(screen.getByLabelText(/Project title/), "Ordering system");
    expect(continueBtn).toBeEnabled();
    await user.click(continueBtn);

    await waitFor(() => {
      expect(created).toMatchObject({ title: "Ordering system", budget_paisa: 0, team_size: 2 });
    });
    // Now on the Requirements step.
    expect(await screen.findByText("Requirements and deadline")).toBeInTheDocument();

    // Back returns to Info without losing the title.
    await user.click(screen.getByRole("button", { name: /Back/ }));
    expect(await screen.findByText("What are you building?")).toBeInTheDocument();
    expect(screen.getByLabelText(/Project title/)).toHaveValue("Ordering system");
  });

  it("surfaces an error when a step cannot be saved", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.get(`${API}/skills`, () => HttpResponse.json(SKILLS)),
      http.post(`${API}/projects`, () =>
        HttpResponse.json(
          { error: { code: "VALIDATION_ERROR", message: "Title is already taken." } },
          { status: 422 },
        ),
      ),
    );
    renderRoutes(routes("/client/projects/new", <CreateProjectPage />), "/client/projects/new");
    await user.type(await screen.findByLabelText(/Project title/), "Ordering system");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    expect(await screen.findByText("That step could not be saved")).toBeInTheDocument();
    expect(screen.getByText("Title is already taken.")).toBeInTheDocument();
  });

  it("walks every step and publishes with a schedule-risk acknowledgement", async () => {
    const user = userEvent.setup();
    const calls: string[] = [];
    let publishBody: unknown = null;
    let verified = false;
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.get(`${API}/me`, () => HttpResponse.json({ ...ME, payment_verified: verified })),
      http.post(`${API}/me/payment-method/verify`, () => {
        verified = true;
        return new HttpResponse(null, { status: 204 });
      }),
      http.get(`${API}/skills`, () => HttpResponse.json(SKILLS)),
      http.post(`${API}/projects`, () =>
        HttpResponse.json({ id: "p1", version: 1, status: "DRAFT" }),
      ),
      http.patch(`${API}/projects/p1`, ({ request }) => {
        calls.push(`patch@${request.headers.get("If-Match") ?? "-"}`);
        return HttpResponse.json({ id: "p1", version: calls.length + 1 });
      }),
      // Never needed: each replace answers with the new version (X-Version).
      http.get(`${API}/projects/p1`, () => {
        calls.push("reread");
        return HttpResponse.json({ id: "p1", version: 99 });
      }),
      // The replaces send If-Match and answer with the bumped version.
      http.put(`${API}/projects/p1/slots`, ({ request }) => {
        calls.push(`slots@${request.headers.get("If-Match") ?? "-"}`);
        return HttpResponse.json([{ id: "s1", skill_id: "s-react", count: 2, label: "" }], {
          headers: { "X-Version": "40" },
        });
      }),
      http.put(`${API}/projects/p1/milestones`, ({ request }) => {
        calls.push(`milestones@${request.headers.get("If-Match") ?? "-"}`);
        return HttpResponse.json([{ id: "m1", name: "Build", position: 0 }], {
          headers: { "X-Version": "41" },
        });
      }),
      http.put(`${API}/projects/p1/dependencies`, ({ request }) => {
        calls.push(`deps@${request.headers.get("If-Match") ?? "-"}`);
        return HttpResponse.json([], { headers: { "X-Version": "42" } });
      }),
      http.post(`${API}/projects/p1/plan/preview`, () => HttpResponse.json(PREVIEW)),
      http.post(`${API}/projects/p1/publish`, async ({ request }) => {
        publishBody = await request.json();
        return HttpResponse.json({ id: "p1", status: "BIDDING" });
      }),
    );
    renderRoutes(
      [
        ...routes("/client/projects/new", <CreateProjectPage />),
        { path: "/client/projects/:id/plan", element: <Probe label="plan-page" /> },
      ],
      "/client/projects/new",
    );

    const next = async () => {
      await user.click(screen.getByRole("button", { name: /Continue/ }));
    };

    // Step 0 — Info
    await user.type(await screen.findByLabelText(/Project title/), "Ordering system");
    await next();

    // Step 1 — Requirements: set a tight 20-day deadline so the plan overruns.
    const deadline = await screen.findByLabelText(/Deadline/);
    await user.clear(deadline);
    await user.type(deadline, "20");
    await next();

    // Step 2 — Skills & team: pick a skill and two of them.
    expect(await screen.findByText("Skills and team")).toBeInTheDocument();
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: "React" }));
    const count = screen.getByLabelText(/How many/);
    await user.clear(count);
    await user.type(count, "2");
    await next();

    // Step 3 — Milestones: name the one milestone (share already 100%).
    expect(await screen.findByText("Plan preview")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^Name/), "Build");
    await screen.findByText("Duration 24 days", {}, { timeout: 3000 });
    await next();

    // Step 4 — Budget
    expect(
      await screen.findByText(/held in escrow and released by milestone/i),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Budget \(৳\)/), "120000");
    await next();

    // Step 5 — Review: the plan overruns, so publish needs the acknowledgement, and a
    // (simulated) payment method must be verified first (D39).
    expect(await screen.findByText("Review and publish")).toBeInTheDocument();
    const publish = screen.getByRole("button", { name: /Publish for bidding/ });
    expect(publish).toBeDisabled();
    await user.click(screen.getByLabelText(/understand the schedule risk/i));
    expect(publish).toBeDisabled(); // still needs a verified payment method
    await user.click(screen.getByRole("button", { name: /Verify payment method/ }));
    expect(await screen.findByText("Payment method verified")).toBeInTheDocument();
    await waitFor(() => {
      expect(publish).toBeEnabled();
    });
    await user.click(publish);

    await waitFor(() => {
      expect(publishBody).toEqual({ acknowledge_schedule_risk: true });
    });
    expect(await screen.findByText("plan-page")).toBeInTheDocument();
    // The draft is patched by its real id; every save sends the version the previous one
    // returned (If-Match), so no re-read is needed (spec §10.1).
    expect(calls).toEqual([
      "patch@1",
      "patch@2",
      "slots@3",
      "milestones@40",
      "deps@41",
      "patch@42",
    ]);
    expect(calls).not.toContain("reread");
  });
});

describe("CreateProjectPage — resuming a draft (D55)", () => {
  const draftProject = {
    id: "p1",
    title: "Ordering system",
    summary: "Order and track restaurant orders.",
    description: "Menu, cart and checkout.",
    requirements: "React and FastAPI.",
    status: "DRAFT",
    start_date: "2026-11-02",
    deadline_days: 30,
    version: 7,
    client_id: "c1",
    budget_paisa: 0,
    bonus_pool_paisa: 0,
    team_size: 2,
    bidding_deadline: null,
    bidding_extensions: 0,
    cancel_reason: null,
    current_baseline_id: null,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
  };
  const milestone = (id: string, name: string, position: number, share: number) => ({
    id,
    name,
    description: "",
    duration_days: 5,
    share_bp: share,
    position,
    status: "PLANNED",
    skill_ids: ["s-react"],
  });

  function wizardAt(path: string, draft: JsonBodyType, status = 200) {
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.get(`${API}/me`, () => HttpResponse.json(ME)),
      http.get(`${API}/skills`, () => HttpResponse.json(SKILLS)),
      http.get(`${API}/projects/p1/draft`, () => HttpResponse.json(draft, { status })),
      http.post(`${API}/projects/p1/plan/preview`, () => HttpResponse.json(PREVIEW)),
      http.patch(`${API}/projects/p1`, () => HttpResponse.json({ id: "p1", version: 8 })),
    );
    return renderRoutes(
      [
        ...routes("/client/projects/new", <CreateProjectPage />),
        { path: "/client/projects/:id/plan", element: <Probe label="plan-page" /> },
      ],
      path,
    );
  }

  it("puts the draft and the step in the address after the first step", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.get(`${API}/skills`, () => HttpResponse.json(SKILLS)),
      http.post(`${API}/projects`, () =>
        HttpResponse.json({ id: "p1", version: 1, status: "DRAFT" }),
      ),
      http.patch(`${API}/projects/p1`, () => HttpResponse.json({ id: "p1", version: 2 })),
    );
    const { router } = renderRoutes(
      routes("/client/projects/new", <CreateProjectPage />),
      "/client/projects/new",
    );
    await user.type(await screen.findByLabelText(/Project title/), "Ordering system");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    expect(await screen.findByText("Requirements and deadline")).toBeInTheDocument();
    await waitFor(() => {
      expect(router.state.location.search).toBe("?draft=p1&step=2");
    });
    // The address update is the wizard's own: it stays on the same step with its data.
    expect(screen.getByText("Requirements and deadline")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Back/ }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("?draft=p1&step=1");
    });
    expect(screen.getByLabelText(/Project title/)).toHaveValue("Ordering system");
  });

  it("reopens a saved draft at the requested step with everything filled in", async () => {
    wizardAt("/client/projects/new?draft=p1&step=4", {
      project: draftProject,
      slots: [{ id: "s1", skill_id: "s-react", count: 2, label: "" }],
      milestones: [milestone("m1", "Design", 0, 4000), milestone("m2", "Build", 1, 6000)],
      dependencies: [{ id: "d1", predecessor_id: "m1", successor_id: "m2" }],
    });
    expect(await screen.findByText("Plan preview")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Design")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Build")).toBeInTheDocument();
    // Build starts after Design: its "after" chip for Design is pressed.
    const after = screen.getAllByRole("button", { name: "Design", pressed: true });
    expect(after).toHaveLength(1);
  });

  it("never resumes past the first step that still needs input", async () => {
    wizardAt("/client/projects/new?draft=p1&step=6", {
      project: draftProject,
      slots: [],
      milestones: [],
      dependencies: [],
    });
    expect(await screen.findByText("Skills and team")).toBeInTheDocument();
  });

  it("restores the info fields and opens the first missing step without a step", async () => {
    const user = userEvent.setup();
    wizardAt("/client/projects/new?draft=p1", {
      project: { ...draftProject, budget_paisa: 0 },
      slots: [{ id: "s1", skill_id: "s-react", count: 2, label: "" }],
      milestones: [milestone("m1", "Design", 0, 10_000)],
      dependencies: [],
    });
    expect(await screen.findByLabelText(/Bidding closes/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Back/ }));
    await user.click(screen.getByRole("button", { name: /Back/ }));
    await user.click(screen.getByRole("button", { name: /Back/ }));
    expect(await screen.findByText("Requirements and deadline")).toBeInTheDocument();
    expect(screen.getByLabelText(/Preferred start/)).toHaveValue("2026-11-02");
    await user.click(screen.getByRole("button", { name: /Back/ }));
    expect(screen.getByLabelText(/Project title/)).toHaveValue("Ordering system");
  });

  it("runs the schedule check when a finished draft reopens on Review", async () => {
    let previewed: unknown = null;
    wizardAt("/client/projects/new?draft=p1&step=6", {
      project: { ...draftProject, budget_paisa: 12_000_000, team_size: 2 },
      slots: [{ id: "s1", skill_id: "s-react", count: 2, label: "" }],
      milestones: [milestone("m1", "Design", 0, 4000), milestone("m2", "Build", 1, 6000)],
      dependencies: [{ id: "d1", predecessor_id: "m1", successor_id: "m2" }],
    });
    // Registered after the helper's handlers, so this preview answer wins.
    server.use(
      http.post(`${API}/projects/p1/plan/preview`, async ({ request }) => {
        previewed = await request.json();
        return HttpResponse.json({ ...PREVIEW, duration: DURATION_40 });
      }),
    );
    expect(await screen.findByText("Review and publish")).toBeInTheDocument();
    expect(await screen.findByText("The plan runs past your deadline")).toBeInTheDocument();
    expect(screen.getByText("40 days")).toBeInTheDocument();
    expect(previewed).toMatchObject({
      team_size: 2,
      slot_count: 2,
      milestones: [
        { key: "m1", predecessor_keys: [] },
        { key: "m2", predecessor_keys: ["m1"] },
      ],
    });
  });

  it("won't continue with a bidding close time in the past", async () => {
    const user = userEvent.setup();
    wizardAt("/client/projects/new?draft=p1&step=5", {
      project: { ...draftProject, budget_paisa: 12_000_000 },
      slots: [{ id: "s1", skill_id: "s-react", count: 2, label: "" }],
      milestones: [milestone("m1", "Design", 0, 10_000)],
      dependencies: [],
    });
    const closes = await screen.findByLabelText(/Bidding closes/);
    await user.type(closes, "2020-01-01T10:00");
    expect(await screen.findByText("Choose a time in the future.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
  });

  it("goes back to the earlier draft with the browser's Back button", async () => {
    const { router } = wizardAt("/client/projects/new?draft=p1&step=2", {
      project: draftProject,
      slots: [],
      milestones: [],
      dependencies: [],
    });
    expect(await screen.findByText("Requirements and deadline")).toBeInTheDocument();
    // The wizard moves a step, so it rewrites the address itself (?draft=p1&step=1).
    await userEvent.click(screen.getByRole("button", { name: /Back/ }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("?draft=p1&step=1");
    });
    await act(async () => {
      await router.navigate("/client/projects/new"); // sidebar "Create project"
    });
    expect(await screen.findByLabelText(/Project title/)).toHaveValue("");
    await act(async () => {
      await router.navigate(-1); // browser Back
    });
    // The draft comes back, not the empty wizard.
    await waitFor(() => {
      expect(screen.getByLabelText(/Project title/)).toHaveValue("Ordering system");
    });
  });

  it("says what's wrong with each number before sending it", async () => {
    const user = userEvent.setup();
    wizardAt("/client/projects/new?draft=p1&step=2", {
      project: draftProject,
      slots: [{ id: "s1", skill_id: "s-react", count: 2, label: "" }],
      milestones: [],
      dependencies: [],
    });
    const deadline = await screen.findByLabelText(/Deadline \(days\)/);
    await user.clear(deadline);
    expect(
      await screen.findByText("Use a whole number of days from 1 to 365."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await user.type(deadline, "400");
    expect(screen.getByText("Use a whole number of days from 1 to 365.")).toBeInTheDocument();
    await user.clear(deadline);
    await user.type(deadline, "30");
    expect(screen.queryByText("Use a whole number of days from 1 to 365.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue/ })).toBeEnabled();
  });

  it("shows the server's field errors next to the fields", async () => {
    const user = userEvent.setup();
    wizardAt("/client/projects/new?draft=p1&step=2", {
      project: draftProject,
      slots: [],
      milestones: [],
      dependencies: [],
    });
    server.use(
      http.patch(`${API}/projects/p1`, () =>
        HttpResponse.json(
          {
            error: {
              code: "VALIDATION_ERROR",
              message: "Some fields need attention.",
              fields: { requirements: "Keep it under 5,000 characters." },
            },
          },
          { status: 422 },
        ),
      ),
    );
    await user.click(await screen.findByRole("button", { name: /Continue/ }));
    expect(await screen.findByText("Keep it under 5,000 characters.")).toBeInTheDocument();
  });

  it("explains a draft that no longer exists", async () => {
    wizardAt(
      "/client/projects/new?draft=p1&step=2",
      { error: { code: "NOT_FOUND", message: "Not found." } },
      404,
    );
    expect(await screen.findByText("This draft isn’t available")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start a new project" })).toHaveAttribute(
      "href",
      "/client/projects/new",
    );
  });

  it("sends a published project to its plan instead of the wizard", async () => {
    wizardAt(
      "/client/projects/new?draft=p1&step=2",
      { error: { code: "INVALID_STATE", message: "Not a draft." } },
      409,
    );
    expect(await screen.findByText("This project is no longer a draft")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View plan" })).toHaveAttribute(
      "href",
      "/client/projects/p1/plan",
    );
  });

  it("offers a retry when the draft can’t be loaded", async () => {
    wizardAt(
      "/client/projects/new?draft=p1",
      { error: { code: "INTERNAL_ERROR", message: "Boom." } },
      500,
    );
    expect(await screen.findByText("We couldn’t open this draft")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Try again/i })).toBeInTheDocument();
  });

  it("starts a fresh wizard when Create project is opened again", async () => {
    const { router } = wizardAt("/client/projects/new?draft=p1&step=2", {
      project: draftProject,
      slots: [],
      milestones: [],
      dependencies: [],
    });
    expect(await screen.findByText("Requirements and deadline")).toBeInTheDocument();
    await act(async () => {
      await router.navigate("/client/projects/new");
    });
    expect(await screen.findByText("What are you building?")).toBeInTheDocument();
    expect(screen.getByLabelText(/Project title/)).toHaveValue("");
    expect(router.state.location.search).toBe("");
  });
});

const PREVIEW = {
  critical_paths: [["Requirements", "Testing"]],
  cycle: null,
  duration: DURATION_24,
  feasible: true,
  nodes: NODES,
  total_share_bp: 10_000,
  warnings: ["This plan runs past the 20-day deadline."],
};

function Harness({ shareBp = 10_000 }: { shareBp?: number }) {
  const [rows, setRows] = useState<MilestoneRow[]>([
    {
      key: "k1",
      name: "Requirements",
      duration_days: 4,
      share_bp: shareBp,
      skill_ids: [],
      predecessor_keys: [],
    },
  ]);
  return (
    <MilestonesStep
      projectId="p1"
      milestones={rows}
      onChange={setRows}
      skills={SKILLS}
      teamSize={3}
      slotCount={2}
      deadlineDays={20}
    />
  );
}

describe("MilestonesStep", () => {
  it("previews the plan, shows warnings, and adds/removes milestones", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.post(`${API}/projects/p1/plan/preview`, () => HttpResponse.json(PREVIEW)),
    );
    renderRoutes([{ path: "/x", element: <Harness /> }], "/x");

    // The debounced preview runs and draws the Gantt with its warning.
    expect(await screen.findByText("Duration 24 days", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText(/runs past the 20-day deadline/i)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Gantt chart/i })).toBeInTheDocument();

    // Switch to the dependency graph and the table.
    await user.click(screen.getByRole("radio", { name: "Graph" }));
    expect(await screen.findByRole("img", { name: /Dependency graph/i })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Table" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();

    // Add a milestone, then remove it.
    await user.click(screen.getByRole("button", { name: /Add milestone/i }));
    expect(screen.getAllByLabelText(/^Name/).length).toBe(2);
    const removeButtons = screen.getAllByRole("button", { name: /Remove/i });
    const lastRemove = removeButtons[removeButtons.length - 1];
    if (lastRemove) await user.click(lastRemove);
    await waitFor(() => {
      expect(screen.getAllByLabelText(/^Name/).length).toBe(1);
    });
  });

  it("shows the share total as incomplete until it reaches 100%", async () => {
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.post(`${API}/projects/p1/plan/preview`, () =>
        HttpResponse.json({ ...PREVIEW, total_share_bp: 6000 }),
      ),
    );
    renderRoutes([{ path: "/x", element: <Harness shareBp={6000} /> }], "/x");
    // The meter reports the partial share (60%), not a tick.
    expect(await screen.findByText(/Share total 60%/)).toBeInTheDocument();
    expect(await screen.findByText("Shares 60%", {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it("warns when the milestones form a dependency cycle", async () => {
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.post(`${API}/projects/p1/plan/preview`, () =>
        HttpResponse.json({
          ...PREVIEW,
          cycle: ["Requirements", "Database", "Requirements"],
          feasible: false,
          duration: NO_DURATION,
          nodes: [],
        }),
      ),
    );
    renderRoutes([{ path: "/x", element: <Harness /> }], "/x");
    expect(
      await screen.findByText(/depend on each other in a loop/i, {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Requirements → Database → Requirements/)).toBeInTheDocument();
  });

  it("lets a later milestone be chosen as a predecessor, so a loop can be shown", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.post(`${API}/projects/p1/plan/preview`, () => HttpResponse.json(PREVIEW)),
    );
    renderRoutes([{ path: "/x", element: <Harness /> }], "/x");
    await user.click(await screen.findByRole("button", { name: /Add milestone/ }));
    const names = screen.getAllByLabelText(/^Name/);
    await user.type(names[1] as HTMLElement, "Database");
    // The first milestone can now depend on the second (a later one).
    const first = screen.getAllByRole("listitem")[0] as HTMLElement;
    expect(within(first).getByRole("button", { name: "Database" })).toBeInTheDocument();
    expect(within(first).queryByRole("button", { name: "Requirements" })).toBeNull(); // not itself
  });

  it("asks before leaving with unsaved changes", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.get(`${API}/skills`, () => HttpResponse.json(SKILLS)),
    );
    const { router } = renderRoutes(
      [
        ...routes("/client/projects/new", <CreateProjectPage />),
        { path: "/client/projects", element: <Probe label="projects-list" /> },
      ],
      "/client/projects/new",
    );
    await user.type(await screen.findByLabelText(/Project title/), "Ordering system");
    void router.navigate("/client/projects");
    const dialog = await screen.findByRole("dialog", { name: "Leave without saving?" });
    await user.click(within(dialog).getByRole("button", { name: "Stay on this step" }));
    expect(screen.getByLabelText(/Project title/)).toHaveValue("Ordering system");
    void router.navigate("/client/projects");
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Leave without saving",
      }),
    );
    expect(await screen.findByText("projects-list")).toBeInTheDocument();
  });
});

/** Render a hook with a throwaway query client (no retries). */
function hookWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return Wrapper;
}

describe("api hooks", () => {
  it("sends If-Match on update, whole-set PUTs, and the lifecycle actions", async () => {
    const seen: Record<string, unknown> = {};
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.patch(`${API}/projects/p1`, ({ request }) => {
        seen.ifMatch = request.headers.get("If-Match");
        return HttpResponse.json({ id: "p1", version: 7 });
      }),
      http.put(`${API}/projects/p1/slots`, ({ request }) => {
        seen.slotsIfMatch = request.headers.get("If-Match");
        return HttpResponse.json([{ id: "s1" }], { headers: { "X-Version": "8" } });
      }),
      http.put(`${API}/projects/p1/milestones`, ({ request }) => {
        seen.milestonesIfMatch = request.headers.get("If-Match");
        return HttpResponse.json([{ id: "m1" }]);
      }),
      http.put(`${API}/projects/p1/dependencies`, () =>
        HttpResponse.json(
          { error: { code: "VERSION_CONFLICT", message: "This project changed." } },
          { status: 409 },
        ),
      ),
      http.post(`${API}/projects/p1/extend-bidding`, () => HttpResponse.json({ id: "p1" })),
      http.delete(`${API}/projects/p1`, () => new HttpResponse(null, { status: 204 })),
    );
    const wrapper = hookWrapper();

    const upd = renderHook(() => hooks.useUpdateProject("p1"), { wrapper });
    await upd.result.current.mutateAsync({ body: { title: "x" }, version: 5 });
    expect(seen.ifMatch).toBe("5");

    const slots = renderHook(() => hooks.useReplaceSlots("p1"), { wrapper });
    const savedSlots = await slots.result.current.mutateAsync({
      slots: [{ skill_id: "s", count: 2, label: "" }],
      version: 7,
    });
    expect(seen.slotsIfMatch).toBe("7");
    expect(savedSlots).toEqual({ items: [{ id: "s1" }], version: 8 });

    const ms = renderHook(() => hooks.useReplaceMilestones("p1"), { wrapper });
    const savedMs = await ms.result.current.mutateAsync({
      milestones: [
        { name: "m", description: "", duration_days: 1, share_bp: 10_000, skill_ids: [] },
      ],
    });
    // No version given: no If-Match, and no X-Version answered → null (the caller re-reads).
    expect(seen.milestonesIfMatch).toBeNull();
    expect(savedMs.version).toBeNull();

    const deps = renderHook(() => hooks.useReplaceDependencies("p1"), { wrapper });
    await expect(
      deps.result.current.mutateAsync({ dependencies: [], version: 1 }),
    ).rejects.toMatchObject({
      code: "VERSION_CONFLICT",
      status: 409,
    });

    const ext = renderHook(() => hooks.useExtendBidding("p1"), { wrapper });
    await ext.result.current.mutateAsync();

    const del = renderHook(() => hooks.useDeleteProject(), { wrapper });
    await del.result.current.mutateAsync("p1");
  });
});
