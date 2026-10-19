/** Projects feature: CPM charts, the create-project wizard, the plan and list pages (Phase 4). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { CpmNode, Skill } from "@/api/types";
import { CpmTable } from "@/components/CpmTable";
import { DependencyGraph } from "@/components/DependencyGraph";
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

  it("renders without a today or deadline line and at a tighter zoom", () => {
    render(<Gantt nodes={NODES} dayWidth={10} />);
    expect(screen.getByRole("img")).toHaveAccessibleName(/24 days/i);
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
    expect(screen.getByText("Requirements")).toBeInTheDocument();
    expect(screen.getByText("Testing")).toBeInTheDocument();
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

describe("MyProjectsPage", () => {
  it("shows the empty state when there are no projects", async () => {
    server.use(http.get(`${API}/projects`, () => HttpResponse.json([])));
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
          : HttpResponse.json([]);
      }),
    );
    renderRoutes(routes("/client/projects", <MyProjectsPage />), "/client/projects");
    await user.click(await screen.findByRole("button", { name: /Try again/i }));
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
  });

  it("lists projects and cancels one with a reason and the typed title", async () => {
    const user = userEvent.setup();
    let cancelled: unknown = null;
    server.use(
      http.get(`${API}/projects`, () =>
        HttpResponse.json([
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

  function planHandlers() {
    server.use(
      http.get(`${API}/projects/p1`, () =>
        HttpResponse.json({
          id: "p1",
          title: "Ordering system",
          status: "BIDDING",
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
    // Toggle to the table alternative.
    await user.click(screen.getByRole("radio", { name: "Table" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
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
      // Re-read after the slot/milestone/dependency replaces (they bump the version).
      http.get(`${API}/projects/p1`, () => {
        calls.push("reread");
        return HttpResponse.json({ id: "p1", version: 40 });
      }),
      http.put(`${API}/projects/p1/slots`, () => {
        calls.push("slots");
        return HttpResponse.json([{ id: "s1", skill_id: "s-react", count: 2, label: "" }]);
      }),
      http.put(`${API}/projects/p1/milestones`, () => {
        calls.push("milestones");
        return HttpResponse.json([{ id: "m1", name: "Build", position: 0 }]);
      }),
      http.put(`${API}/projects/p1/dependencies`, () => {
        calls.push("deps");
        return HttpResponse.json([]);
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
    // The draft is patched by its real id, and the budget PATCH carries the re-read version.
    expect(calls).toContain("reread");
    expect(calls).toContain("patch@40");
    expect(calls).toContain("slots");
    expect(calls).toContain("milestones");
    expect(calls).toContain("deps");
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
      http.put(`${API}/projects/p1/slots`, () => HttpResponse.json([{ id: "s1" }])),
      http.put(`${API}/projects/p1/milestones`, () => HttpResponse.json([{ id: "m1" }])),
      http.put(`${API}/projects/p1/dependencies`, () => HttpResponse.json([])),
      http.post(`${API}/projects/p1/extend-bidding`, () => HttpResponse.json({ id: "p1" })),
      http.delete(`${API}/projects/p1`, () => new HttpResponse(null, { status: 204 })),
    );
    const wrapper = hookWrapper();

    const upd = renderHook(() => hooks.useUpdateProject("p1"), { wrapper });
    await upd.result.current.mutateAsync({ body: { title: "x" }, version: 5 });
    expect(seen.ifMatch).toBe("5");

    const slots = renderHook(() => hooks.useReplaceSlots("p1"), { wrapper });
    await slots.result.current.mutateAsync([{ skill_id: "s", count: 2, label: "" }]);

    const ms = renderHook(() => hooks.useReplaceMilestones("p1"), { wrapper });
    await ms.result.current.mutateAsync([
      { name: "m", description: "", duration_days: 1, share_bp: 10_000, skill_ids: [] },
    ]);

    const deps = renderHook(() => hooks.useReplaceDependencies("p1"), { wrapper });
    await deps.result.current.mutateAsync([]);

    const ext = renderHook(() => hooks.useExtendBidding("p1"), { wrapper });
    await ext.result.current.mutateAsync();

    const del = renderHook(() => hooks.useDeleteProject(), { wrapper });
    await del.result.current.mutateAsync("p1");
  });
});
