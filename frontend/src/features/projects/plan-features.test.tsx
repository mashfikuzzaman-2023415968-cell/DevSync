/** Spec §13.5 #21/#22 and §13.3 composites: the wizard's money breakdown and bonus pool, the
 * Review step's plan, the Gantt's month zoom and the dependency graph's milestone panel. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, type JsonBodyType } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import type { CpmNode } from "@/api/types";
import { DependencyGraph } from "@/components/DependencyGraph";
import { Gantt } from "@/components/Gantt";
import { afterFee, bpOf, bpPercent } from "@/lib/money";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import CreateProjectPage from "./CreateProjectPage";
import { bonusPctProblem } from "./schemas";

const API = "https://testserver/api/v1";

const NODES: CpmNode[] = [
  { key: "a", name: "Requirements", es: 0, ef: 4, ls: 0, lf: 4, slack: 0, critical: true },
  { key: "b", name: "Database", es: 4, ef: 9, ls: 4, lf: 9, slack: 0, critical: true },
  { key: "c", name: "Backend API", es: 9, ef: 17, ls: 9, lf: 17, slack: 0, critical: true },
  {
    key: "d",
    name: "Frontend",
    es: 4,
    ef: 13,
    ls: 8,
    lf: 17,
    slack: 4,
    critical: false,
    share_bp: 2500,
  },
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
// Named so the motion lint rule doesn't read schedule data as an animation timing.
const DURATION_24 = 24;
const NO_DURATION = 0;

const longNode = (days: number): CpmNode => ({
  key: "x",
  name: "Platform build",
  es: 0,
  ef: days,
  ls: 0,
  lf: days,
  slack: 0,
  critical: true,
});

describe("money helpers", () => {
  it("takes basis points of an amount, rounding half up in whole paisa", () => {
    expect(bpOf(12_000_000, 1000)).toBe(1_200_000);
    expect(bpOf(12_345, 5000)).toBe(6173); // 6,172.5 rounds up
    expect(bpOf(12_345, 1)).toBe(1); // 1.2345
    expect(bpOf(0, 1000)).toBe(0);
    expect(bpOf(10_000_000_000, 5000)).toBe(5_000_000_000); // the server's largest budget
    expect(bpOf(-5, 100)).toBe(0);
    expect(bpOf(1.5, 100)).toBe(0);
  });

  it("leaves the team the budget minus the fee, rounded down like the server", () => {
    expect(afterFee(12_000_000, 500)).toBe(11_400_000);
    expect(afterFee(12_345, 500)).toBe(11_727); // 11,727.75 rounds down; the fee gets 618
    expect(afterFee(100, 0)).toBe(100);
    expect(afterFee(100, 10_000)).toBe(0);
    expect(afterFee(100, 20_000)).toBe(0); // clamped
    expect(afterFee(100, Number.NaN)).toBe(100);
    expect(afterFee(-1, 500)).toBe(0);
  });

  it("formats basis points with at most one decimal", () => {
    expect(bpPercent(500)).toBe("5%");
    expect(bpPercent(1250)).toBe("12.5%");
    expect(bpPercent(9990)).toBe("99.9%");
  });
});

describe("bonusPctProblem", () => {
  it("accepts 0 to 50 with at most one decimal", () => {
    for (const ok of ["0", "10", "12.5", "50", " 7 "]) expect(bonusPctProblem(ok)).toBeUndefined();
  });

  it("refuses empty, negative, too large and too precise values", () => {
    expect(bonusPctProblem("")).toMatch(/Enter a percentage/);
    for (const bad of ["50.1", "51", "-1", "12.55", "1e1", "abc", "."]) {
      expect(bonusPctProblem(bad)).toBe("Use 0 to 50%, with at most one decimal.");
    }
  });
});

describe("Gantt month zoom", () => {
  it("labels month starts with the year on the first one and on each January", async () => {
    const user = userEvent.setup();
    render(<Gantt nodes={[longNode(130)]} startDate="2026-11-01" />);
    await user.click(screen.getByRole("radio", { name: "Months" }));
    expect(screen.getByRole("radio", { name: "Months" })).toBeChecked();
    expect(screen.getByText("Nov 2026")).toBeInTheDocument();
    expect(screen.getByText("Dec")).toBeInTheDocument();
    expect(screen.getByText("Jan 2027")).toBeInTheDocument();
    expect(screen.getByText("Feb")).toBeInTheDocument();
  });

  it("names the year on the first visible month when the start label has no room", async () => {
    const user = userEvent.setup();
    // Starts 28 Nov: the "Nov" label would sit 3 days before "Dec", so only "Dec" shows.
    render(<Gantt nodes={[longNode(100)]} startDate="2026-11-28" />);
    await user.click(screen.getByRole("radio", { name: "Months" }));
    expect(screen.getByText("Dec 2026")).toBeInTheDocument();
    expect(screen.queryByText("Nov 2026")).not.toBeInTheDocument();
  });

  it("counts 30-day months without a start date", async () => {
    const user = userEvent.setup();
    render(<Gantt nodes={[longNode(100)]} />);
    await user.click(screen.getByRole("radio", { name: "Months" }));
    expect(screen.getByText("Months", { selector: "text" })).toBeInTheDocument();
    expect(screen.getByText("Month 1")).toBeInTheDocument();
    expect(screen.getByText("Month 4")).toBeInTheDocument();
    expect(screen.queryByText("Month 5")).not.toBeInTheDocument();
  });

  it("starts plans longer than 180 days in months, and up to 180 in weeks", () => {
    const { unmount } = render(<Gantt nodes={[longNode(181)]} />);
    expect(screen.getByRole("radio", { name: "Months" })).toBeChecked();
    unmount();
    render(<Gantt nodes={[longNode(180)]} />);
    expect(screen.getByRole("radio", { name: "Weeks" })).toBeChecked();
  });

  it("keeps an explicit zoom and can go back to days", async () => {
    const user = userEvent.setup();
    render(<Gantt nodes={NODES} zoom="months" startDate="2026-11-02" />);
    expect(screen.getByRole("radio", { name: "Months" })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: "Days" }));
    expect(screen.getByRole("radio", { name: "Days" })).toBeChecked();
    // Day numbers are back on the axis.
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
  });
});

describe("DependencyGraph milestone panel", () => {
  it("opens a panel with the schedule, dates, share and dependencies on click", async () => {
    const user = userEvent.setup();
    render(
      <DependencyGraph
        nodes={NODES}
        edges={EDGES}
        startDate="2026-11-02"
        budgetPaisa={12_000_000}
      />,
    );
    await user.click(screen.getByLabelText("Frontend"));
    const panel = await screen.findByRole("dialog", { name: "Frontend" });
    const p = within(panel);
    expect(p.getByText("Can slip 4 days without delaying the finish.")).toBeInTheDocument();
    expect(p.getByText("Duration").nextSibling).toHaveTextContent("9 days");
    expect(p.getByText("Earliest start").nextSibling).toHaveTextContent("Day 4 (6 Nov 2026)");
    // The finish is the last working day, like the Gantt (offsets [4, 13) end on 14 Nov).
    expect(p.getByText("Earliest finish").nextSibling).toHaveTextContent("Day 12 (14 Nov 2026)");
    expect(p.getByText("Latest start").nextSibling).toHaveTextContent("Day 8 (10 Nov 2026)");
    expect(p.getByText("Latest finish").nextSibling).toHaveTextContent("Day 16 (18 Nov 2026)");
    expect(p.getByText("Slack").nextSibling).toHaveTextContent("4 days");
    expect(p.getByText("Share of budget").nextSibling).toHaveTextContent("25% (৳30,000)");
    const dependsOn = p.getByText("Depends on").parentElement as HTMLElement;
    expect(within(dependsOn).getByText("Requirements")).toBeInTheDocument();
    const neededBy = p.getByText("Needed by").parentElement as HTMLElement;
    expect(within(neededBy).getByText("Integration")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("opens from the keyboard with Enter or Space and says when a milestone is critical", async () => {
    const user = userEvent.setup();
    render(<DependencyGraph nodes={NODES} edges={EDGES} />);
    await user.tab();
    expect(document.activeElement).toHaveAccessibleName("Requirements, on the critical path");
    expect(document.activeElement).toHaveAccessibleDescription(/Press Enter/);
    await user.keyboard("{Enter}");
    const panel = await screen.findByRole("dialog", { name: "Requirements" });
    expect(
      within(panel).getByText("On the critical path, so any delay moves the finish date."),
    ).toBeInTheDocument();
    // No start date: days only. Nothing comes before the first milestone.
    expect(within(panel).getByText("Earliest start").nextSibling).toHaveTextContent(/^Day 0$/);
    expect(within(panel).getByText("Slack").nextSibling).toHaveTextContent("None");
    expect(within(panel).getByText("Nothing, so it can start right away.")).toBeInTheDocument();
    expect(within(panel).queryByText("Share of budget")).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    // Focus comes back to the node, so Space reopens it.
    await waitFor(() => {
      expect(document.activeElement).toHaveAccessibleName("Requirements, on the critical path");
    });
    await user.keyboard(" ");
    expect(await screen.findByRole("dialog", { name: "Requirements" })).toBeInTheDocument();
  });

  it("ignores other keys and shows only the dependencies without schedule data", async () => {
    const user = userEvent.setup();
    render(
      <DependencyGraph
        nodes={[
          { key: "a", name: "Design", critical: false },
          { key: "b", name: "Build", critical: false },
        ]}
        edges={[
          ["a", "b"],
          ["a", "ghost"],
        ]}
      />,
    );
    await user.tab();
    await user.keyboard("x");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByLabelText("Build"));
    const panel = await screen.findByRole("dialog", { name: "Build" });
    expect(within(panel).getByText("Not on the critical path.")).toBeInTheDocument();
    expect(within(panel).queryByText("Duration")).not.toBeInTheDocument();
    expect(within(panel).getByText("Design")).toBeInTheDocument();
    expect(
      within(panel).getByText("Nothing waits for it, so it ends the plan."),
    ).toBeInTheDocument();
  });

  it("shows the share without an amount when the budget isn't set", async () => {
    const user = userEvent.setup();
    render(<DependencyGraph nodes={NODES} edges={EDGES} budgetPaisa={0} />);
    await user.click(screen.getByLabelText("Frontend"));
    const panel = await screen.findByRole("dialog", { name: "Frontend" });
    expect(within(panel).getByText("Share of budget").nextSibling).toHaveTextContent(/^25%$/);
  });
});

// ------------------------------------------------------------------------------- wizard

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
  payment_verified: true,
  created_at: "2026-10-17T00:00:00Z",
};
const SKILLS = [{ id: "s-react", name: "React", domain: "FRONTEND" }];
const PREVIEW = {
  critical_paths: [["Requirements", "Testing"]],
  cycle: null,
  duration: DURATION_24,
  feasible: true,
  nodes: NODES,
  total_share_bp: 10_000,
  warnings: [],
  platform_fee_bp: 500,
  bonus_pool_bp: 1000,
};
const draftProject = {
  id: "p1",
  title: "Ordering system",
  summary: "",
  description: "",
  requirements: "",
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
const twoMilestones = {
  slots: [{ id: "s1", skill_id: "s-react", count: 2, label: "" }],
  milestones: [milestone("a", "Requirements", 0, 4000), milestone("b", "Database", 1, 6000)],
  dependencies: [{ id: "d1", predecessor_id: "a", successor_id: "b" }],
};

function routes(path: string, element: ReactNode) {
  return [
    { path, element },
    { path: "/client/projects/:id/plan", element: <Probe label="plan-page" /> },
    { path: "*", element: <Probe label="elsewhere" /> },
  ];
}

function wizardAt(path: string, draft: JsonBodyType, preview: JsonBodyType = PREVIEW) {
  const patches: unknown[] = [];
  server.use(
    http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
    http.get(`${API}/me`, () => HttpResponse.json(ME)),
    http.get(`${API}/skills`, () => HttpResponse.json(SKILLS)),
    http.get(`${API}/projects/p1/draft`, () => HttpResponse.json(draft)),
    http.post(`${API}/projects/p1/plan/preview`, () => HttpResponse.json(preview)),
    http.patch(`${API}/projects/p1`, async ({ request }) => {
      patches.push(await request.json());
      return HttpResponse.json({ id: "p1", version: 8 });
    }),
  );
  renderRoutes(routes("/client/projects/new", <CreateProjectPage />), path);
  return patches;
}

const breakdown = () => screen.getByRole("region", { name: "Where the money goes" });
const row = (label: string) => within(breakdown()).getByText(label).nextSibling as HTMLElement;

describe("CreateProjectPage — budget step", () => {
  it("shows the fee, what reaches the team and the total, and saves the bonus in paisa", async () => {
    const user = userEvent.setup();
    const patches = wizardAt("/client/projects/new?draft=p1&step=5", {
      project: draftProject,
      ...twoMilestones,
    });
    const budget = await screen.findByLabelText(/Budget \(৳\)/);
    expect(screen.getByText(/Enter a budget to see the platform fee/)).toBeInTheDocument();
    await user.type(budget, "120000");
    await waitFor(() => {
      expect(row("Platform fee (5%)")).toHaveTextContent("৳6,000");
    });
    expect(row("Reaches the team, paid by milestone")).toHaveTextContent("৳1,14,000");
    expect(row("You fund in total")).toHaveTextContent("৳1,20,000");
    expect(screen.queryByLabelText(/Bonus pool \(% of budget\)/)).not.toBeInTheDocument();

    // Turning the pool on starts at the platform's suggestion (pay.bonus_pool_bp = 10%).
    await user.click(screen.getByRole("switch", { name: /Add a bonus pool/ }));
    const pct = screen.getByLabelText(/Bonus pool \(% of budget\)/);
    expect(pct).toHaveValue(10);
    expect(row("Bonus pool (10%)")).toHaveTextContent("৳12,000");
    expect(row("You fund in total")).toHaveTextContent("৳1,32,000");

    // Boundaries: above 50% and two decimals are refused; Continue waits for a valid value.
    const cont = screen.getByRole("button", { name: /Continue/ });
    await user.clear(pct);
    expect(screen.getByText(/Enter a percentage, or turn the bonus pool off/)).toBeInTheDocument();
    expect(cont).toBeDisabled();
    await user.type(pct, "50.5");
    expect(screen.getByText("Use 0 to 50%, with at most one decimal.")).toBeInTheDocument();
    expect(cont).toBeDisabled();
    await user.clear(pct);
    await user.type(pct, "12.5");
    expect(row("Bonus pool (12.5%)")).toHaveTextContent("৳15,000");
    expect(cont).toBeEnabled();
    await user.click(cont);
    await waitFor(() => {
      expect(patches).toContainEqual(
        expect.objectContaining({ budget_paisa: 12_000_000, bonus_pool_paisa: 1_500_000 }),
      );
    });
    expect(await screen.findByText("Review and publish")).toBeInTheDocument();
  });

  it("saves no bonus when the pool is switched off again", async () => {
    const user = userEvent.setup();
    const patches = wizardAt("/client/projects/new?draft=p1&step=5", {
      project: { ...draftProject, budget_paisa: 12_000_000, bonus_pool_paisa: 1_200_000 },
      ...twoMilestones,
    });
    const toggle = await screen.findByRole("switch", { name: /Add a bonus pool/ });
    expect(toggle).toBeChecked();
    expect(screen.getByLabelText(/Bonus pool \(% of budget\)/)).toHaveValue(10);
    await user.click(toggle);
    expect(screen.queryByLabelText(/Bonus pool \(% of budget\)/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await waitFor(() => {
      expect(patches).toContainEqual(expect.objectContaining({ bonus_pool_paisa: 0 }));
    });
  });

  it("takes the fee from the platform settings, not a fixed 5%", async () => {
    wizardAt(
      "/client/projects/new?draft=p1&step=5",
      { project: { ...draftProject, budget_paisa: 12_000_000 }, ...twoMilestones },
      { ...PREVIEW, platform_fee_bp: 750 },
    );
    await screen.findByLabelText(/Budget \(৳\)/);
    await waitFor(() => {
      expect(row("Platform fee (7.5%)")).toHaveTextContent("৳9,000");
    });
    expect(row("Reaches the team, paid by milestone")).toHaveTextContent("৳1,11,000");
    expect(screen.getByRole("switch", { name: /Add a bonus pool/ })).not.toBeChecked();
  });

  it("derives the percentage from an uneven saved bonus", async () => {
    wizardAt("/client/projects/new?draft=p1&step=5", {
      project: { ...draftProject, budget_paisa: 12_000_000, bonus_pool_paisa: 1_000_000 },
      ...twoMilestones,
    });
    // 1,000,000 / 12,000,000 = 8.33…% → 8.3%
    expect(await screen.findByLabelText(/Bonus pool \(% of budget\)/)).toHaveValue(8.3);
  });
});

describe("CreateProjectPage — review step", () => {
  const ready = { ...draftProject, budget_paisa: 12_000_000 };

  it("shows the generated plan as a Gantt or a table, with the critical path", async () => {
    const user = userEvent.setup();
    wizardAt("/client/projects/new?draft=p1&step=6", { project: ready, ...twoMilestones });
    expect(await screen.findByText("Review and publish")).toBeInTheDocument();
    expect(await screen.findByText("Duration 24 days")).toBeInTheDocument();
    expect(screen.getByText("5 critical milestones")).toBeInTheDocument();
    expect(screen.getByText("Shares 100%")).toBeInTheDocument();
    const gantt = screen.getByRole("img", { name: /Gantt chart/ });
    // One arrow per dependency in the draft (Requirements → Database).
    expect(gantt.querySelectorAll("path[marker-end]")).toHaveLength(1);
    await user.click(screen.getByRole("radio", { name: "Table" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Publish for bidding/ })).toBeEnabled();
  });

  it("warns about a loop and blocks publishing", async () => {
    wizardAt(
      "/client/projects/new?draft=p1&step=6",
      { project: ready, ...twoMilestones },
      {
        ...PREVIEW,
        feasible: false,
        duration: NO_DURATION,
        nodes: [],
        cycle: ["Requirements", "Database"],
      },
    );
    expect(
      await screen.findByText("These milestones depend on each other in a loop"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Requirements → Database/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Gantt chart/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Publish for bidding/ })).toBeDisabled();
  });

  it("warns when the shares don't total 100% and blocks publishing", async () => {
    wizardAt(
      "/client/projects/new?draft=p1&step=6",
      { project: ready, ...twoMilestones },
      { ...PREVIEW, total_share_bp: 9990 },
    );
    expect(await screen.findByText("Milestone shares don’t add up to 100%")).toBeInTheDocument();
    expect(screen.getByText(/They total 99.9%/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Publish for bidding/ })).toBeDisabled();
  });

  it("offers a retry when the schedule check fails", async () => {
    const user = userEvent.setup();
    let calls = 0;
    wizardAt("/client/projects/new?draft=p1&step=6", { project: ready, ...twoMilestones });
    server.use(
      http.post(`${API}/projects/p1/plan/preview`, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ error: { code: "INTERNAL_ERROR", message: "x" } }, { status: 500 })
          : HttpResponse.json(PREVIEW);
      }),
    );
    expect(await screen.findByText("We couldn’t check the schedule")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Try again/i }));
    expect(await screen.findByText("Duration 24 days")).toBeInTheDocument();
  });
});
