/** Profile, portfolio, challenges, timed test and public profile screens (spec §17 Phase 3). */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import ChallengesPage from "@/features/challenges/ChallengesPage";
import TestPage from "@/features/challenges/TestPage";
import SettingsPage from "@/features/account/SettingsPage";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import ProfilePage from "./ProfilePage";
import PublicProfilePage from "./PublicProfilePage";
import { aboutSchema, isGithubUsername, isHttpsUrl, itemSchema, reviewSchema } from "./schemas";
import { changedFields } from "./useAutosave";

const ME = {
  id: "dev-1",
  email: "nadia@example.com",
  phone_e164: "+8801712345678",
  display_name: "Nadia Rahman",
  role: "DEVELOPER",
  status: "ACTIVE",
  email_verified: true,
  phone_verified: true,
  totp_enabled: false,
  totp_verified: false,
  created_at: "2026-10-01T00:00:00Z",
};
const SKILLS = [
  { id: "s-react", name: "React", domain: "FRONTEND" },
  { id: "s-pg", name: "PostgreSQL", domain: "DATABASE" },
];
const PROFILE = {
  headline: "React developer",
  bio: "",
  hours_per_week: 20,
  github_username: null,
  timezone: "Asia/Dhaka",
  visibility: "PUBLIC",
  skills: [{ skill_id: "s-react", name: "React", domain: "FRONTEND", self_level: 4 }],
  updated_at: null,
};
const item = (id: string, title: string, position: number) => ({
  id,
  title,
  description: "",
  url: null,
  skill_ids: [],
  position,
  images: [],
});
const TEST = {
  id: "t-react",
  skill_id: "s-react",
  skill_name: "React",
  title: "React fundamentals",
  question_count: 2,
  time_limit_seconds: 600,
  last_score: null,
  last_attempt_at: null,
  next_attempt_at: null,
  open_attempt_id: null,
};
const ATTEMPT = {
  id: "a-1",
  test_id: "t-react",
  title: "React fundamentals",
  started_at: new Date().toISOString(),
  deadline_at: new Date(Date.now() + 600_000).toISOString(),
  server_now: new Date().toISOString(),
  submitted_at: null,
  score: null,
  questions: [
    {
      id: "q1",
      ordinal: 0,
      text: "Which hook runs effects?",
      options: ["useMemo", "useEffect", "useRef", "useId"],
    },
    {
      id: "q2",
      ordinal: 1,
      text: "What does JSX compile to?",
      options: ["HTML", "Function calls", "CSS", "JSON"],
    },
  ],
  answers: {},
};

const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });
const base = (over: { portfolio?: unknown[]; me?: object | null } = {}) => [
  csrf(),
  http.get("*/api/v1/me", () =>
    over.me === null
      ? HttpResponse.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 })
      : HttpResponse.json({ ...ME, ...over.me }),
  ),
  http.get("*/api/v1/skills", () => HttpResponse.json(SKILLS)),
  http.get("*/api/v1/me/developer-profile", () => HttpResponse.json(PROFILE)),
  http.get("*/api/v1/me/portfolio", () => HttpResponse.json(over.portfolio ?? [])),
  http.get("*/api/v1/me/certificates", () => HttpResponse.json([])),
  http.get("*/api/v1/me/external-reviews", () => HttpResponse.json([])),
  http.get("*/api/v1/skill-tests", () => HttpResponse.json([TEST])),
];

describe("profile schemas", () => {
  it("accepts https only and GitHub username rules", () => {
    expect(isHttpsUrl("")).toBe(true);
    expect(isHttpsUrl("https://example.com/a?b=1")).toBe(true);
    for (const bad of ["http://example.com", "javascript:alert(1)", "https://", "https://a b.com"])
      expect(isHttpsUrl(bad)).toBe(false);
    expect(isGithubUsername("nadia-dev")).toBe(true);
    for (const bad of ["-x", "x-", "a--b", "a_b", "a".repeat(40)])
      expect(isGithubUsername(bad)).toBe(false);
  });

  it("bounds hours, headline length and review dates", () => {
    const ok = {
      headline: "",
      bio: "",
      hours_per_week: 1,
      github_username: "",
      timezone: "Asia/Dhaka",
      visibility: "PUBLIC",
    };
    expect(aboutSchema.safeParse(ok).success).toBe(true);
    expect(aboutSchema.safeParse({ ...ok, hours_per_week: 0 }).success).toBe(false);
    expect(aboutSchema.safeParse({ ...ok, hours_per_week: 81 }).success).toBe(false);
    expect(aboutSchema.safeParse({ ...ok, headline: "x".repeat(121) }).success).toBe(false);
    expect(
      itemSchema.safeParse({ title: "  ", description: "", url: "", skill_ids: [] }).success,
    ).toBe(false);
    const review = { source: "Upwork", rating: "4.8", scale: "5", project_date: "2026-01-01" };
    expect(reviewSchema.safeParse(review).success).toBe(true);
    expect(reviewSchema.safeParse({ ...review, rating: "6" }).success).toBe(false);
    expect(reviewSchema.safeParse({ ...review, project_date: "2999-01-01" }).success).toBe(false);
  });

  it("autosave sends only changed fields", () => {
    expect(changedFields({ a: 1, b: "x" }, { a: 1, b: "y" })).toEqual({ b: "x" });
    expect(changedFields({ a: 1 }, { a: 1 })).toEqual({});
  });
});

describe("ProfilePage", () => {
  it("autosaves the headline with only that field and says Saved", async () => {
    const bodies: unknown[] = [];
    server.use(
      ...base(),
      http.patch("*/api/v1/me/developer-profile", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        bodies.push(body);
        return HttpResponse.json({ ...PROFILE, ...body, updated_at: "2026-10-18T05:00:00Z" });
      }),
    );
    renderRoutes([{ path: "/dev/profile", element: <ProfilePage /> }], "/dev/profile");
    const headline = await screen.findByLabelText("Headline");
    await userEvent.clear(headline);
    await userEvent.type(headline, "Accessible React forms");
    await waitFor(() => { expect(screen.getByText("Saved")).toBeInTheDocument(); }, { timeout: 3000 });
    expect(bodies.at(-1)).toEqual({ headline: "Accessible React forms" });
    expect(screen.getByRole("link", { name: /View public profile/ })).toHaveAttribute(
      "href",
      "/d/dev-1",
    );
  });

  it("shows the server's field error and Not saved", async () => {
    server.use(
      ...base(),
      http.patch("*/api/v1/me/developer-profile", () =>
        HttpResponse.json(
          {
            error: {
              code: "VALIDATION_ERROR",
              message: "Some fields need attention.",
              fields: { github_username: "Use a GitHub username." },
            },
          },
          { status: 422 },
        ),
      ),
    );
    renderRoutes([{ path: "/", element: <ProfilePage /> }], "/");
    await userEvent.type(await screen.findByLabelText("GitHub username"), "nadia");
    expect(
      await screen.findByText("Use a GitHub username.", {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(screen.getByText("Not saved.")).toBeInTheDocument();
  });

  it("shows the empty portfolio with a call to add the first item", async () => {
    server.use(...base());
    renderRoutes([{ path: "/", element: <ProfilePage /> }], "/");
    expect(await screen.findByText("Show your first piece of work")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add a portfolio item" }));
    expect(await screen.findByRole("dialog", { name: "Add a portfolio item" })).toBeInTheDocument();
  });

  it("moves an item down from its menu (keyboard-friendly reorder)", async () => {
    let order: unknown;
    server.use(
      ...base({ portfolio: [item("p1", "First", 0), item("p2", "Second", 1)] }),
      http.put("*/api/v1/me/portfolio-order", async ({ request }) => {
        order = await request.json();
        return HttpResponse.json([item("p2", "Second", 0), item("p1", "First", 1)]);
      }),
    );
    renderRoutes([{ path: "/", element: <ProfilePage /> }], "/");
    await userEvent.click(await screen.findByRole("button", { name: "Actions for First" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Move down" }));
    await waitFor(() => { expect(order).toEqual({ ids: ["p2", "p1"] }); });
  });

  it("shows an error state with Try again when the profile fails to load", async () => {
    server.use(...base());
    server.use(
      http.get("*/api/v1/me/developer-profile", () =>
        HttpResponse.json(
          { error: { code: "INTERNAL_ERROR", request_id: "req_9" } },
          { status: 500 },
        ),
      ),
    );
    renderRoutes([{ path: "/", element: <ProfilePage /> }], "/");
    expect(await screen.findByText("This didn’t load")).toBeInTheDocument();
    expect(screen.getByText("req_9")).toBeInTheDocument();
  });
});

describe("Challenges and the timed test", () => {
  it("starts a test after confirming and opens the attempt", async () => {
    server.use(
      ...base(),
      http.post("*/api/v1/skill-tests/t-react/attempts", () =>
        HttpResponse.json(ATTEMPT, { status: 201 }),
      ),
    );
    renderRoutes(
      [
        { path: "/dev/challenges", element: <ChallengesPage /> },
        { path: "/dev/challenges/test/:attemptId", element: <Probe label="test page" /> },
      ],
      "/dev/challenges",
    );
    await userEvent.click(await screen.findByRole("button", { name: "Start test" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/keeps running if you leave/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Start the timer" }));
    expect(await screen.findByText("test page")).toBeInTheDocument();
  });

  it("shows when a locked test is available again", async () => {
    server.use(...base());
    server.use(
      http.get("*/api/v1/skill-tests", () =>
        HttpResponse.json([
          {
            ...TEST,
            last_score: "0.800",
            last_attempt_at: "2026-10-10T05:00:00Z",
            next_attempt_at: "2026-11-09T05:00:00Z",
          },
        ]),
      ),
    );
    renderRoutes([{ path: "/", element: <ChallengesPage /> }], "/");
    expect(await screen.findByText(/Available again 9 Nov 2026/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Your last React score" })).toHaveAttribute(
      "aria-valuenow",
      "80",
    );
    expect(screen.queryByRole("button", { name: "Start test" })).toBeNull();
  });

  it("saves each answer, then submits and shows the score without the answers", async () => {
    const answers: unknown[] = [];
    server.use(
      csrf(),
      http.get("*/api/v1/attempts/a-1", () => HttpResponse.json(ATTEMPT)),
      http.post("*/api/v1/attempts/a-1/answer", async ({ request }) => {
        answers.push(await request.json());
        return HttpResponse.json({ question_id: "q1", choice: 1, answered: 1 });
      }),
      http.post("*/api/v1/attempts/a-1/submit", () =>
        HttpResponse.json({
          id: "a-1",
          score: "0.500",
          correct: 1,
          total: 2,
          submitted_at: "2026-10-18T05:05:00Z",
          added_to_profile: true,
        }),
      ),
    );
    renderRoutes([{ path: "/t/:attemptId", element: <TestPage /> }], "/t/a-1");
    expect(await screen.findByText("Question 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("timer")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "useEffect" }));
    await waitFor(() => { expect(answers).toEqual([{ question_id: "q1", choice: 1 }]); });
    await userEvent.click(screen.getByRole("button", { name: "Next question" }));
    expect(screen.getByText("What does JSX compile to?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Submit test" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/You answered 1 of 2 questions/)).toBeInTheDocument();
    server.use(
      http.get("*/api/v1/attempts/a-1", () =>
        HttpResponse.json({ ...ATTEMPT, submitted_at: "2026-10-18T05:05:00Z", score: "0.500" }),
      ),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Submit test" }));
    expect(await screen.findByText("1 of 2 correct")).toBeInTheDocument();
    expect(screen.getByText(/Added to your profile/)).toBeInTheDocument();
    expect(screen.queryByText(/correct answer/i)).toBeNull();
  });

  it("says when an attempt isn't found", async () => {
    server.use(
      http.get("*/api/v1/attempts/a-x", () =>
        HttpResponse.json({ error: { code: "NOT_FOUND" } }, { status: 404 }),
      ),
    );
    renderRoutes([{ path: "/t/:attemptId", element: <TestPage /> }], "/t/a-x");
    expect(await screen.findByText("We couldn’t find this test")).toBeInTheDocument();
  });
});

describe("PublicProfilePage", () => {
  const PUBLIC = {
    id: "dev-1",
    display_name: "Nadia Rahman",
    member_since: "2026-10-01T00:00:00Z",
    headline: "React developer",
    bio: "<script>alert(1)</script>",
    hours_per_week: 20,
    github_username: "nadia-dev",
    visibility: "PUBLIC",
    skills: [{ skill_id: "s-react", name: "React", domain: "FRONTEND", self_level: 4 }],
    verified_scores: [
      { skill_id: "s-react", name: "React", score: "0.800", at: "2026-10-10T00:00:00Z" },
    ],
    portfolio: [
      {
        id: "p1",
        title: "Clinic app",
        description: "",
        url: null,
        skill_ids: ["s-react"],
        image_ids: ["f1"],
      },
    ],
    certificates: [],
  };

  it("renders the profile for anonymous visitors, user text as text", async () => {
    server.use(
      ...base({ me: null }),
      http.get("*/api/v1/public/developers/dev-1", () => HttpResponse.json(PUBLIC)),
    );
    renderRoutes([{ path: "/d/:id", element: <PublicProfilePage /> }], "/d/dev-1");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Nadia Rahman" }),
    ).toBeInTheDocument();
    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Clinic app, screenshot" })).toHaveAttribute(
      "src",
      "/api/v1/files/f1/download",
    );
    expect(screen.getByRole("link", { name: "nadia-dev" })).toHaveAttribute(
      "href",
      "https://github.com/nadia-dev",
    );
    expect(screen.getByText("Strong (4 of 5)")).toBeInTheDocument();
  });

  it("explains a hidden profile and offers client sign-in", async () => {
    server.use(
      ...base({ me: null }),
      http.get("*/api/v1/public/developers/dev-2", () =>
        HttpResponse.json({ error: { code: "NOT_FOUND" } }, { status: 404 }),
      ),
    );
    renderRoutes([{ path: "/d/:id", element: <PublicProfilePage /> }], "/d/dev-2");
    expect(await screen.findByText("This profile isn’t available")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in as a client" })).toHaveAttribute(
      "href",
      "/login?return_to=%2Fd%2Fdev-2",
    );
  });
});

describe("Client profile in Settings", () => {
  it("saves the organisation for clients and rejects an http website", async () => {
    let body: unknown;
    server.use(
      ...base({ me: { role: "CLIENT", id: "c-1" } }),
      http.get("*/api/v1/auth/sessions", () => HttpResponse.json({ items: [] })),
      http.get("*/api/v1/me/client-profile", () =>
        HttpResponse.json({ organization: "", description: "", website: null, updated_at: null }),
      ),
      http.patch("*/api/v1/me/client-profile", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          organization: "Rahim Traders",
          description: "",
          website: null,
          updated_at: null,
        });
      }),
    );
    renderRoutes([{ path: "/", element: <SettingsPage /> }], "/");
    const org = await screen.findByLabelText("Organisation");
    await userEvent.type(org, "Rahim Traders");
    await userEvent.type(screen.getByLabelText("Website"), "http://example.com");
    await userEvent.click(screen.getByRole("button", { name: "Save organisation" }));
    expect(await screen.findByText("Use a full https:// address.")).toBeInTheDocument();
    expect(body).toBeUndefined();
    await userEvent.clear(screen.getByLabelText("Website"));
    await userEvent.click(screen.getByRole("button", { name: "Save organisation" }));
    await waitFor(() => { expect(body).toEqual({ organization: "Rahim Traders", description: "", website: "" }); },
    );
  });
});
