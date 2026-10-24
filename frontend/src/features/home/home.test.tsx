/** Role dashboards (spec §13.5 #9 and #20): real stats, next actions, activity, the
 * recommended strip, recent bids, reputation stat cards and every data state. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, type JsonBodyType } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { renderRoutes } from "@/test/render";
import ClientHome from "./ClientHome";
import DeveloperHome from "./DeveloperHome";

const API = "*/api/v1";

const ME = {
  id: "u-1",
  email: "rahim@example.com",
  display_name: "Rahim Uddin",
  role: "CLIENT",
  status: "ACTIVE",
  phone_e164: "+8801712345678",
  phone_verified: true,
  email_verified: true,
  payment_verified: true,
  totp_enabled: false,
  totp_verified: false,
  created_at: "2026-10-01T00:00:00Z",
};

function project(id: string, status: string, updated: string, extra: object = {}) {
  return {
    id,
    title: `Project ${id}`,
    status,
    budget_paisa: 12_000_000,
    deadline_days: 30,
    team_size: 3,
    bidding_deadline: null,
    updated_at: updated,
    ...extra,
  };
}

const PROJECTS = [
  project("draft", "DRAFT", "2026-10-20T00:00:00Z"),
  project("bid", "BIDDING", "2026-10-22T00:00:00Z", {
    bidding_deadline: "2026-11-02T06:00:00Z",
  }),
  project("form", "FORMING", "2026-10-19T00:00:00Z"),
  project("run", "IN_PROGRESS", "2026-10-18T00:00:00Z"),
  project("hold", "ON_HOLD", "2026-10-17T00:00:00Z"),
  project("done", "COMPLETED", "2026-10-16T00:00:00Z"),
  project("gone", "CANCELLED", "2026-10-23T00:00:00Z"),
  project("old", "COMPLETED", "2026-09-01T00:00:00Z"),
];

const fail = () =>
  HttpResponse.json({ error: { code: "INTERNAL", request_id: "req-2" } }, { status: 500 });

function client(projects: JsonBodyType, me: object = {}) {
  server.use(
    http.get(`${API}/me`, () => HttpResponse.json({ ...ME, ...me })),
    http.get(`${API}/projects`, () => HttpResponse.json(projects)),
  );
  return renderRoutes([{ path: "/client", element: <ClientHome /> }], "/client");
}

/** The card around a stat label. */
function stat(label: string): HTMLElement {
  const card = screen.getByText(label, { selector: "p" }).closest("div.rounded-lg");
  if (!(card instanceof HTMLElement)) throw new Error(`no stat card ${label}`);
  return card;
}

function statValue(label: string): string | null | undefined {
  return stat(label).querySelector(".sr-only")?.textContent;
}

function cardOf(title: string): HTMLElement {
  const card = screen.getByRole("heading", { level: 2, name: title }).closest("div.rounded-lg");
  if (!(card instanceof HTMLElement)) throw new Error(`no card ${title}`);
  return card;
}

describe("ClientHome", () => {
  it("counts the client's real projects", async () => {
    client(PROJECTS);
    expect(await screen.findByText("Your projects")).toBeInTheDocument();
    // Active = FORMING + IN_PROGRESS + ON_HOLD; one draft; one bidding; two completed.
    expect(statValue("Active projects")).toBe("3");
    expect(statValue("Open for bids")).toBe("1");
    expect(statValue("Drafts")).toBe("1");
    expect(statValue("Completed")).toBe("2");
    expect(screen.queryByText("No projects yet")).not.toBeInTheDocument();
  });

  it("lists up to six, newest first, without cancelled ones, each with its next action", async () => {
    client(PROJECTS);
    await screen.findByText("Your projects");
    const card = cardOf("Your projects");
    const titles = within(card)
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(titles).toEqual([
      "Project bid",
      "Project draft",
      "Project form",
      "Project run",
      "Project hold",
      "Project done",
    ]);
    expect(within(card).queryByText("Project gone")).not.toBeInTheDocument();
    expect(
      within(card).getByRole("link", { name: "Continue editing: Project draft" }),
    ).toHaveAttribute("href", "/client/projects/new?draft=draft");
    expect(within(card).getByRole("link", { name: "See bids: Project bid" })).toHaveAttribute(
      "href",
      "/client/projects/bid/bids",
    );
    expect(within(card).getByRole("link", { name: "See bids: Project form" })).toHaveAttribute(
      "href",
      "/client/projects/form/bids",
    );
    expect(within(card).getByRole("link", { name: "View plan: Project run" })).toHaveAttribute(
      "href",
      "/client/projects/run/plan",
    );
    expect(within(card).getByText(/bids close 2 Nov 2026/)).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "My projects" })).toHaveAttribute(
      "href",
      "/client/projects",
    );
  });

  it("shows recent activity in words with the full date in a title", async () => {
    client(PROJECTS);
    await screen.findByText("Recent activity");
    const items = within(cardOf("Recent activity")).getAllByRole("listitem");
    expect(items).toHaveLength(5);
    expect(items[0]).toHaveTextContent("Project gone");
    expect(items[0]).toHaveTextContent("Cancelled");
    expect(items[1]).toHaveTextContent("Open for bids");
    const time = items[1]?.querySelector("time");
    expect(time).toHaveAttribute("datetime", "2026-10-22T00:00:00Z");
    expect(time?.getAttribute("title")).toMatch(/22 Oct 2026/);
  });

  it("hides the checklist once both checks are done", async () => {
    client(PROJECTS);
    await screen.findByText("Your projects");
    expect(screen.queryByText("Before you publish")).not.toBeInTheDocument();
  });

  it("keeps the checklist while a verification is missing", async () => {
    client(PROJECTS, { phone_verified: false });
    expect(await screen.findByText("Before you publish")).toBeInTheDocument();
    expect(screen.getByText("Your projects")).toBeInTheDocument();
  });

  it("keeps the empty state when there are no projects", async () => {
    client([], { email_verified: false });
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Plan your first project" })).toBeInTheDocument();
    expect(screen.getByText("Before you publish")).toBeInTheDocument();
    expect(screen.queryByText("Active projects")).not.toBeInTheDocument();
  });

  it("explains when every project was cancelled", async () => {
    client([project("gone", "CANCELLED", "2026-10-23T00:00:00Z")]);
    expect(await screen.findByText(/Every project so far was cancelled/)).toBeInTheDocument();
    expect(statValue("Active projects")).toBe("0");
  });

  it("shows an error with retry, then recovers", async () => {
    const user = userEvent.setup();
    let failing = true;
    server.use(
      http.get(`${API}/me`, () => HttpResponse.json(ME)),
      http.get(`${API}/projects`, () => (failing ? fail() : HttpResponse.json(PROJECTS))),
    );
    renderRoutes([{ path: "/client", element: <ClientHome /> }], "/client");
    expect(await screen.findByText("Your projects didn’t load")).toBeInTheDocument();
    failing = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Your projects")).toBeInTheDocument();
  });

  it("shows a skeleton while loading", async () => {
    server.use(
      http.get(`${API}/me`, () => HttpResponse.json(ME)),
      http.get(`${API}/projects`, () => new Promise<Response>(() => undefined)),
    );
    const { container } = renderRoutes([{ path: "/client", element: <ClientHome /> }], "/client");
    expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(container.querySelector('[aria-hidden="true"]')).toBeTruthy();
    expect(screen.queryByText("No projects yet")).not.toBeInTheDocument();
    expect(screen.queryByText("Your projects")).not.toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------- developer

const DEV_ME = { ...ME, id: "d-1", display_name: "Nadia Rahman", role: "DEVELOPER" };

const CARD = {
  id: "p-1",
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

function bid(id: string, status: string, created: string) {
  return {
    id,
    project_id: `proj-${id}`,
    project_title: `Bid project ${id}`,
    slot_id: "s",
    slot_label: "React developer",
    status,
    price_paisa: 1_800_000,
    days_needed: 20,
    hours_per_week_committed: 20,
    proposal: "",
    expected_contribution: "",
    portfolio_item_ids: [],
    created_at: created,
    updated_at: created,
    version: 1,
    evaluated_at: null,
    reasons: [],
  };
}

const PROFILE = {
  id: "d-1",
  display_name: "Nadia Rahman",
  member_since: "2026-10-01T00:00:00Z",
  headline: "",
  bio: "",
  hours_per_week: 20,
  github_username: null,
  visibility: "PUBLIC",
  skills: [],
  verified_scores: [],
  portfolio: [],
  certificates: [],
};

const EXPERIENCED = {
  competency: "0.712",
  performance: "0.768",
  is_newcomer: false,
  seeded: true,
};
const NEWCOMER = { competency: null, performance: null, is_newcomer: true, seeded: false };

function developer(
  opts: {
    reputation?: object | null;
    recommended?: unknown;
    bids?: ReturnType<typeof bid>[];
    failRecommended?: boolean;
    failBids?: boolean;
    failProfile?: boolean;
  } = {},
) {
  server.use(
    http.get(`${API}/me`, () => HttpResponse.json(DEV_ME)),
    http.get(`${API}/me/portfolio`, () => HttpResponse.json([])),
    http.get(`${API}/skill-tests`, () => HttpResponse.json([])),
    // Like the server: newest first, optional status filter, a page of `limit` (§10.1).
    http.get(`${API}/me/bids`, ({ request }) => {
      if (opts.failBids) return fail();
      const params = new URL(request.url).searchParams;
      const status = params.get("status");
      const limit = Number(params.get("limit") ?? "20");
      const items = (opts.bids ?? [])
        .filter((b) => !status || b.status === status)
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .slice(0, limit);
      return HttpResponse.json({ items, next_cursor: null });
    }),
    http.get(`${API}/projects/recommended`, () =>
      opts.failRecommended ? fail() : HttpResponse.json(opts.recommended ?? []),
    ),
    http.get(`${API}/developers/d-1`, () =>
      opts.failProfile
        ? fail()
        : HttpResponse.json({
            ...PROFILE,
            reputation: opts.reputation === undefined ? NEWCOMER : opts.reputation,
          }),
    ),
  );
  return renderRoutes([{ path: "/dev", element: <DeveloperHome /> }], "/dev");
}

describe("DeveloperHome", () => {
  it("shows competency and performance on 0–100 with the seeded note", async () => {
    developer({ reputation: EXPERIENCED });
    expect(await screen.findByText("Competency")).toBeInTheDocument();
    expect(statValue("Competency")).toBe("71");
    expect(statValue("Performance")).toBe("77");
    expect(screen.getAllByText("Seeded for the demo")).toHaveLength(2);
    // Known not to be a newcomer: the checklist is gone.
    expect(screen.queryByText("Get ready for your first team")).not.toBeInTheDocument();
  });

  it("says a newcomer is building a record and keeps the checklist", async () => {
    developer();
    expect(await screen.findByText("Building your record")).toBeInTheDocument();
    expect(screen.queryByText("Competency", { selector: "p" })).not.toBeInTheDocument();
    expect(screen.getByText("Get ready for your first team")).toBeInTheDocument();
  });

  it("offers a retry when the record fails to load", async () => {
    const user = userEvent.setup();
    developer({ failProfile: true });
    expect(await screen.findByText("Couldn’t load your record")).toBeInTheDocument();
    expect(screen.getByText("Get ready for your first team")).toBeInTheDocument();
    server.use(
      http.get(`${API}/developers/d-1`, () =>
        HttpResponse.json({ ...PROFILE, reputation: EXPERIENCED }),
      ),
    );
    const card = screen.getByText("Couldn’t load your record").closest("div.rounded-lg");
    if (!(card instanceof HTMLElement)) throw new Error("no record card");
    await user.click(within(card).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Competency")).toBeInTheDocument();
  });

  it("counts only active bids and lists the latest five", async () => {
    developer({
      bids: [
        bid("1", "ACTIVE", "2026-10-10T00:00:00Z"),
        bid("2", "WITHDRAWN", "2026-10-11T00:00:00Z"),
        bid("3", "ACTIVE", "2026-10-12T00:00:00Z"),
        bid("4", "NOT_SELECTED", "2026-10-13T00:00:00Z"),
        bid("5", "INELIGIBLE", "2026-10-14T00:00:00Z"),
        bid("6", "SELECTED", "2026-10-15T00:00:00Z"),
      ],
    });
    expect(await screen.findByText("Bid project 6")).toBeInTheDocument();
    expect(statValue("Open bids")).toBe("2");
    const card = cardOf("Recent bids");
    const links = within(card)
      .getAllByRole("link")
      .filter((a) => a.textContent.startsWith("Bid project"));
    expect(links.map((a) => a.textContent)).toEqual([
      "Bid project 6",
      "Bid project 5",
      "Bid project 4",
      "Bid project 3",
      "Bid project 2",
    ]);
    expect(links[0]).toHaveAttribute("href", "/dev/bids/6");
    expect(within(card).getByText("Not selected")).toBeInTheDocument();
    expect(within(card).queryByText("Bid project 1")).not.toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "All bids" })).toHaveAttribute(
      "href",
      "/dev/bids",
    );
  });

  it("shows empty bids and recommendations", async () => {
    developer();
    expect(await screen.findByText("No bids yet")).toBeInTheDocument();
    expect(await screen.findByText("No matches right now")).toBeInTheDocument();
    expect(statValue("Open bids")).toBe("0");
  });

  it("links each recommended project with budget, deadline and matched skills", async () => {
    developer({
      recommended: [
        {
          project: CARD,
          skill_match_count: 2,
          matched_skills: ["FastAPI", "React"],
          typical_days: null,
        },
      ],
    });
    const link = await screen.findByRole("link", { name: /Online ordering system/ });
    expect(link).toHaveAttribute("href", "/dev/projects/p-1");
    expect(link).toHaveTextContent("৳1,20,000 budget, 30 days to deliver");
    expect(within(link).getByText("FastAPI")).toBeInTheDocument();
    expect(within(link).getByText("React")).toBeInTheDocument();
  });

  it("shows errors for recommendations and bids with retry", async () => {
    developer({ failRecommended: true, failBids: true });
    expect(await screen.findByText("Recommendations didn’t load")).toBeInTheDocument();
    expect(await screen.findByText("Your bids didn’t load")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Try again" }).length).toBeGreaterThanOrEqual(2);
  });
});
