/** Reputation page (screen 16), ReputationPanel, RadarChart, TrendChart and the label helpers:
 * all four data states, newcomer vs experienced, chart table alternatives, keyboard details,
 * and plain words only on the page (no paper symbols outside the "How it’s calculated" drawer). */
import { render as rtlRender, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { DeveloperReputation, ReputationHistoryItem } from "@/api/types";
import { RadarChart } from "@/components/RadarChart";
import { ReputationPanel } from "@/components/ReputationPanel";
import { TrendChart } from "@/components/TrendChart";
import { domainLabel, PARAMETER_BY_KEY, PARAMETERS, toNumber } from "@/lib/reputation";
import { server } from "@/test/server";
import { renderRoutes } from "@/test/render";
import ReputationPage from "./ReputationPage";

const API = "https://testserver/api/v1";
const ME = { id: "d1", role: "DEVELOPER", display_name: "Arif Hossain" };

const experienced = (over: Partial<DeveloperReputation> = {}): DeveloperReputation => ({
  developer_id: "d1",
  parameters: { omega: "0.786", x: "0.860", xm: "0.686", beta: "0.748", mu: "0.857", t: "0.549" },
  competency: "0.808",
  performance: "0.726",
  completed_projects: 8,
  distinct_clients: 5,
  is_newcomer: false,
  seeded: false,
  simulated: true,
  skills: [],
  newcomer: null,
  updated_at: "2026-11-21T09:00:00Z",
  ...over,
});

const newcomer = (): DeveloperReputation =>
  experienced({
    parameters: { omega: "0.200", x: "0.600", xm: "0.500", beta: "0.664", mu: "0.500", t: "0.500" },
    competency: "0.320",
    performance: "0.582",
    completed_projects: 1,
    distinct_clients: 1,
    is_newcomer: true,
    simulated: false,
    newcomer: { verified_items: 4, evidence_domains: 1, review_default: "0.664", threshold: 3 },
  });

const item = (n: number, over: Partial<ReputationHistoryItem> = {}): ReputationHistoryItem => ({
  history_id: `h${String(n)}`,
  project_label: `Project ${String(n)}`,
  domain: "FRONTEND",
  completed_at: `2025-0${String(n)}-10T06:00:00Z`,
  simulated: true,
  changes: [
    { parameter: "t", old: "0.500", new: "0.333", raw_new: "0.333", capped: false,
      reason: "Punctuality 50 → 33: finished in 20 of 30 days." },
    { parameter: "mu", old: "0.500", new: "0.500", raw_new: "0.500", capped: false,
      reason: "Client diversity stays 50: work for a new client (1 client over 1 project)." },
    { parameter: "c", old: "0.400", new: `0.${String(40 + n)}0`, raw_new: "0.450", capped: false,
      reason: "Competency 40 → 45: follows from expertise and communication." },
    { parameter: "p", old: "0.550", new: `0.${String(50 + n)}0`, raw_new: "0.580", capped: false,
      reason: "Performance 55 → 58: follows from quality, client diversity and punctuality." },
  ],
  ...over,
}); // prettier-ignore

function mock(rep: DeveloperReputation | null, items: ReputationHistoryItem[] | "error" = []) {
  server.use(
    http.get(`${API}/me`, () => HttpResponse.json(ME)),
    http.get(`${API}/developers/d1/reputation`, () =>
      rep
        ? HttpResponse.json(rep)
        : HttpResponse.json(
            { error: { code: "INTERNAL_ERROR", request_id: "r-7" } },
            { status: 500 },
          ),
    ),
    http.get(`${API}/me/reputation/history`, () =>
      items === "error"
        ? HttpResponse.json(
            { error: { code: "INTERNAL_ERROR", request_id: "r-8" } },
            { status: 500 },
          )
        : HttpResponse.json({ items, next_cursor: null }),
    ),
  );
}

function renderPage() {
  return renderRoutes(
    [{ path: "/dev/reputation", element: <ReputationPage /> }],
    "/dev/reputation",
  );
}

describe("ReputationPage", () => {
  it("shows a skeleton while loading", () => {
    mock(experienced());
    renderPage();
    expect(screen.getByLabelText("Loading your reputation")).toHaveAttribute("aria-busy", "true");
  });

  it("shows an error with the request id and a retry", async () => {
    mock(null);
    renderPage();
    expect(await screen.findByText("Your reputation didn’t load")).toBeInTheDocument();
    expect(screen.getByText("r-7")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Try again/ })).toBeInTheDocument();
  });

  it("shows an experienced developer's parameters, labels and simulated note", async () => {
    mock(experienced(), [item(3), item(2), item(1)]);
    renderPage();
    expect(
      await screen.findByText("Based on 8 completed projects for 5 clients."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Simulated history").length).toBeGreaterThan(0);
    expect(screen.getByText(/market simulator/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Expertise 79 of 100" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Punctuality 55 of 100" })).toBeInTheDocument();
    expect(screen.getByText("81")).toBeInTheDocument(); // competency 0.808
    expect(screen.queryByText("Where your starting values come from")).not.toBeInTheDocument();
    expect(screen.queryByText("Seeded demo value")).not.toBeInTheDocument();
  });

  it("explains each change in plain words, newest project first, hiding unchanged ones", async () => {
    mock(experienced(), [item(3), item(2), item(1)]);
    renderPage();
    const why = (await screen.findByText("Why did this change?")).closest("[data-card]");
    expect(why).not.toBeNull();
    const headings = within(why as HTMLElement).getAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual(["Project 3", "Project 2", "Project 1"]);
    expect(
      within(why as HTMLElement).getAllByText("Punctuality 50 → 33: finished in 20 of 30 days."),
    ).toHaveLength(3);
    expect(
      within(why as HTMLElement).queryByText(/Client diversity stays/),
    ).not.toBeInTheDocument();
  });

  it("shows the first five projects and expands to all", async () => {
    const items = [7, 6, 5, 4, 3, 2, 1].map((n) => item(n));
    mock(experienced(), items);
    renderPage();
    expect(await screen.findByText("Project 7")).toBeInTheDocument();
    expect(screen.queryByText("Project 2")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show all 7 projects" }));
    expect(screen.getByText("Project 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show the latest 5 projects" })).toBeInTheDocument();
  });

  it("explains a newcomer's starting values", async () => {
    mock(newcomer(), [item(1, { simulated: false })]);
    renderPage();
    expect(await screen.findByText("You’re a newcomer: 1 of 3 projects done.")).toBeInTheDocument();
    expect(screen.getByText("Where your starting values come from")).toBeInTheDocument();
    expect(screen.getByText(/4 of 4 verified items/)).toBeInTheDocument();
    expect(screen.getByText(/passed a skill check in 1 area\./)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Complete your profile" })).toHaveAttribute(
      "href",
      "/dev/profile",
    );
    expect(
      await screen.findByText("Your trend appears after your second project."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Simulated history")).not.toBeInTheDocument();
  });

  it("shows the empty state when there are no completed projects", async () => {
    mock(newcomer(), []);
    renderPage();
    expect(await screen.findByText("No completed projects yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Find projects" })).toHaveAttribute(
      "href",
      "/dev/find",
    );
  });

  it("shows a history error without hiding the parameters", async () => {
    mock(experienced(), "error");
    renderPage();
    expect(await screen.findByText("Your reputation history didn’t load")).toBeInTheDocument();
    expect(screen.getByText("Your parameters")).toBeInTheDocument();
  });

  it("marks seeded demo values", async () => {
    mock(experienced({ seeded: true, simulated: false }), []);
    renderPage();
    expect(await screen.findByText("Seeded demo value")).toBeInTheDocument();
  });

  it("uses plain words outside the calculation drawer", async () => {
    mock(experienced(), [item(2), item(1)]);
    const { container } = renderPage();
    await screen.findByText("Why did this change?");
    expect(container.textContent).not.toMatch(/[ωβμ]|Eq\./);
  });
});

describe("ReputationPanel", () => {
  it("shows 'Building a record' when another user's newcomer has no values", () => {
    const rep = experienced({
      parameters: { omega: null, x: null, xm: null, beta: null, mu: null, t: null },
      competency: null,
      performance: null,
      is_newcomer: true,
    });
    rtlRender(<ReputationPanel reputation={rep} />);
    expect(screen.getByText("Building a record")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("groups parameters and opens the explanations", async () => {
    rtlRender(<ReputationPanel reputation={experienced()} showEvidence />);
    expect(screen.getByRole("heading", { name: "Competency" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Performance" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Teamwork" })).toBeInTheDocument();
    expect(screen.getAllByRole("progressbar")).toHaveLength(6);
    await userEvent.click(screen.getByRole("button", { name: "How it’s calculated" }));
    expect(screen.getByText("Expertise = ω")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "What punctuality means" }));
    expect(screen.getByText(/late work scores 0/)).toBeInTheDocument();
  });

  it("stays compact without evidence", () => {
    rtlRender(<ReputationPanel reputation={experienced()} />);
    expect(screen.queryByRole("button", { name: "How it’s calculated" })).not.toBeInTheDocument();
  });
});

describe("RadarChart", () => {
  const axes = PARAMETERS.map((p, i) => ({ label: p.label, value: (i + 2) / 10 }));

  it("describes the chart and switches to a table", async () => {
    rtlRender(<RadarChart title="Six parameters" axes={axes} />);
    expect(
      screen.getByRole("img", { name: /Six parameters: Expertise 20, Communication 30/ }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "View as table" }));
    const table = screen.getByRole("table");
    expect(within(table).getByRole("rowheader", { name: "Punctuality" })).toBeInTheDocument();
    expect(within(table).getByText("70")).toBeInTheDocument();
  });

  it("clamps out-of-range values", () => {
    rtlRender(
      <RadarChart
        title="Clamped"
        axes={[
          { label: "A", value: 2 },
          { label: "B", value: -1 },
          { label: "C", value: 0.5 },
        ]}
      />,
    );
    expect(screen.getByRole("img", { name: "Clamped: A 100, B 0, C 50" })).toBeInTheDocument();
  });
});

describe("TrendChart", () => {
  const points = [
    { label: "First", detail: "1 Jan 2025" },
    { label: "Second" },
    { label: "Third" },
  ];
  const series = [
    { name: "Competency", values: [0.4, 0.5, 0.62] },
    { name: "Performance", values: [0.55, null, 0.64] },
  ];

  it("shows a project's values on focus, keyboard first", async () => {
    rtlRender(<TrendChart title="Trend" points={points} series={series} />);
    expect(screen.getByText(/Point at, tap or tab/)).toBeInTheDocument();
    await userEvent.tab(); // the chart/table switch
    await userEvent.tab();
    expect(
      screen.getByText("First (1 Jan 2025): Competency 40, Performance 55"),
    ).toBeInTheDocument();
    await userEvent.tab();
    expect(screen.getByText("Second: Competency 50")).toBeInTheDocument();
  });

  it("has a legend and a table alternative with gaps marked", async () => {
    rtlRender(<TrendChart title="Trend" points={points} series={series} />);
    expect(screen.getByText("Competency")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "View as table" }));
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(4);
    expect(within(rows[2] as HTMLElement).getByText("—")).toBeInTheDocument();
  });
});

describe("reputation labels", () => {
  it("parses decimal strings safely", () => {
    expect(toNumber("0.808")).toBe(0.808);
    expect(toNumber(null)).toBeNull();
    expect(toNumber(undefined)).toBeNull();
    expect(toNumber("not a number")).toBeNull();
  });

  it("names domains and parameters in plain words", () => {
    expect(domainLabel("FRONTEND")).toBe("Front-end");
    expect(domainLabel("UNKNOWN")).toBe("UNKNOWN");
    expect(PARAMETER_BY_KEY.t.label).toBe("Punctuality");
    expect(PARAMETERS.map((p) => p.label)).toEqual([
      "Expertise", "Communication", "Teamwork", "Quality", "Client diversity", "Punctuality",
    ]); // prettier-ignore
  });
});
