/**
 * Screens that a plain `goto` cannot reach (spec §13.14, §16.5 steps 13–15): they need an
 * account in a particular state, an object id or a step of a flow. `screens.ts` lists the
 * screens with a fixed address; these carry the preparation with them, so the axe scan, the
 * responsive matrix and the visual baselines all cover the same set.
 *
 * Each screen's `prepare` leaves the browser where it needs to be and says how to open the
 * screen again at the next viewport: a `path` for screens that survive a reload, or an `open`
 * step for those that do not (the admin's two-step verification page, which exists only between
 * the password and the code).
 */
import { expect, type Page } from "@playwright/test";
import {
  addReputationHistory,
  addRoleResult,
  addSkillEvidence,
  apiSignIn,
  createOrderingProject,
  csrfHeaders,
  throughAuthZone,
  lastLink,
  PASSWORD,
  roleAnswerKey,
  seedUser,
  setReputation,
  slotFor,
} from "./fixtures";
import { resetLimits } from "./test";

/** How to show a screen again (after a viewport or colour-scheme change). */
export type Reach = { path: string; open?: undefined } | { open: (page: Page) => Promise<void> };

export interface StatefulScreen {
  name: string;
  /** Build the state the screen needs; returns how to open it. */
  prepare: (page: Page, baseURL: string) => Promise<Reach>;
  /**
   * The screen's own content differs on every run, so it gets no pixel baseline: the timed test
   * draws ten questions at random per attempt (`test_questions_are_random_per_attempt` holds the
   * server to that), and questions of different lengths change every card's height, which masking
   * cannot hide. The visual run still opens the screen; the axe scan and the responsive matrix
   * cover it in full.
   */
  randomContent?: boolean;
}

/** Open a screen described by `Reach` (and wait for the page to settle). */
export async function openScreen(page: Page, reach: Reach): Promise<void> {
  await resetLimits(page.request);
  if (reach.open) await reach.open(page);
  else await page.goto(reach.path);
  await page.waitForLoadState("networkidle");
}

/** A newcomer with React on their profile, on a published project's bid sheet with the React
 * role chosen (the bid draft keeps the choice in sessionStorage across reloads). */
async function newcomerOnBidSheet(page: Page, baseURL: string, name: string): Promise<string> {
  await apiSignIn(page, baseURL, "CLIENT", "Rahim Uddin");
  const projectId = await createOrderingProject(page, baseURL, { publish: true });
  const dev = await apiSignIn(page, baseURL, "DEVELOPER", name);
  await addSkillEvidence(page.request, baseURL, dev.userId, "React", 0.7);
  await page.goto(`/dev/projects/${projectId}`);
  await page.getByRole("combobox").click();
  await page.getByRole("option", { name: "React" }).first().click();
  await page.getByText("Role assessment required").waitFor();
  return `/dev/projects/${projectId}`;
}

async function openConsent(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await page.getByRole("button", { name: "Start assessment" }).click();
  await page.getByRole("dialog", { name: "Before you start" }).waitFor();
  await settled(page);
}

/** Wait for running animations: measured mid-zoom or mid-fade, an overlay's buttons are a few
 * pixels short and its text (or the page behind it) reads as low contrast. */
async function settled(page: Page): Promise<void> {
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running"),
  );
}

export const STATEFUL_SCREENS: StatefulScreen[] = [
  {
    // Phase 6: an experienced developer's reputation computed from six simulated projects
    // (fixed simulator seed and dates, so the page is the same on every run).
    name: "reputation-experienced",
    prepare: async (page, baseURL) => {
      const dev = await apiSignIn(page, baseURL, "DEVELOPER", "Arif Hossain");
      await addReputationHistory(page.request, baseURL, dev.userId, 6);
      return { path: "/dev/reputation" };
    },
  },
  {
    // Where a new account lands: "verify your email and phone" with both codes outstanding.
    name: "verify",
    prepare: async (page, baseURL) => {
      await apiSignIn(page, baseURL, "DEVELOPER", "Nadia Rahman", { verified: false });
      return { path: "/verify" };
    },
  },
  {
    // The page the email link opens, with a real (single-use) token.
    name: "verify-email",
    prepare: async (page, baseURL) => {
      // Seeding an account writes no email, so ask for one: the resend needs the pending
      // account's own session and the bot check the endpoint requires (D68).
      const user = await apiSignIn(page, baseURL, "DEVELOPER", "Nadia Rahman", {
        verified: false,
      });
      const sent = await page.request.post("/api/v1/auth/email/resend", {
        headers: await csrfHeaders(page.request, baseURL),
        data: { captcha: "test-bypass" },
      });
      if (!sent.ok())
        throw new Error(
          `verification email not sent: ${String(sent.status())} ${await sent.text()}`,
        );
      const link = await lastLink(page.request, user.email, "verify_email");
      if (!link) throw new Error(`no verify_email link for ${user.email}`);
      const url = new URL(link);
      return { path: `${url.pathname}${url.search}` };
    },
  },
  {
    // The admin's second factor: reached with the password, never by address (the page sends a
    // visitor without a pre-auth token back to sign-in), so it is re-opened through the form.
    name: "login-totp",
    prepare: async (page, baseURL) => {
      const admin = await seedUser(page.request, baseURL, "ADMIN", "Admin User");
      const open = async (target: Page) => {
        await target.goto("/login");
        await target.getByLabel("Email").fill(admin.email);
        await target.getByLabel("Password", { exact: true }).fill(PASSWORD);
        await target.getByRole("button", { name: /Sign in|Checking/ }).click();
        await target.getByRole("heading", { name: "Two-step verification" }).waitFor();
      };
      await open(page);
      return { open };
    },
  },
  {
    // An administrator who has not set a second factor up yet (§14.4): the only page they may
    // use until they do.
    name: "admin-setup-2fa",
    prepare: async (page, baseURL) => {
      await apiSignIn(page, baseURL, "ADMIN", "Admin User", { withTotp: false });
      return { path: "/admin/setup-2fa" };
    },
  },
  {
    // The timed practice test, with the countdown running and the first question shown.
    name: "timed-test",
    randomContent: true,
    prepare: async (page, baseURL) => {
      await apiSignIn(page, baseURL, "DEVELOPER", "Nadia Rahman");
      await page.goto("/dev/challenges");
      await page
        .getByRole("group", { name: "React skill test" })
        .getByRole("button", { name: "Start test" })
        .click();
      await page.getByRole("button", { name: "Start the timer" }).click();
      await page.waitForURL(/\/dev\/challenges\/test\//, { timeout: 15_000 });
      await page.getByText("Question 1 of 10").waitFor();
      return { path: new URL(page.url()).pathname };
    },
  },
  {
    // The role assessment a newcomer needs before bidding (role assessment spec §11.2).
    name: "assessment-required",
    prepare: async (page, baseURL) => ({
      path: await newcomerOnBidSheet(page, baseURL, "Nadia Rahman"),
    }),
  },
  {
    // The rules, accepted before an attempt starts (§7.1).
    name: "assessment-consent",
    prepare: async (page, baseURL) => {
      const path = await newcomerOnBidSheet(page, baseURL, "Nadia Rahman");
      return { open: (p) => openConsent(p, path) };
    },
  },
  {
    // The runner on its first question (§11.3); questions are drawn per attempt. The matrix
    // reopens this screen at every viewport, so the page acts like a browser without full screen
    // (the focus layout iPhones get): a full-screen window can't be resized, and leaving full
    // screen is a leave. Reopening reuses the open runner instead of reloading — a reload is a
    // leave too, and two would end the attempt (both rules are tested in role-assessment.spec).
    name: "assessment-runner",
    randomContent: true,
    prepare: async (page, baseURL) => {
      await page.addInitScript(() => {
        (Element.prototype as { requestFullscreen?: unknown }).requestFullscreen = undefined;
      });
      const path = await newcomerOnBidSheet(page, baseURL, "Nadia Rahman");
      await openConsent(page, path);
      const consent = page.getByRole("dialog", { name: "Before you start" });
      await consent.getByRole("checkbox", { name: "I understand and agree" }).click();
      await consent.getByRole("button", { name: "Start assessment" }).click();
      await page.getByTestId("assessment-runner").getByText("Question 1 of 12").waitFor();
      return {
        open: async (p) => {
          const runner = p.getByTestId("assessment-runner");
          if (!(await runner.isVisible())) {
            await p.goto(path);
            await p.getByRole("button", { name: "Resume assessment" }).click();
          }
          await runner.getByText(/Question \d+ of 12/).waitFor();
          await settled(p);
        },
      };
    },
  },
  {
    // A finished role assessment's result (§11.4): every answer right, so the page is stable.
    name: "assessment-result",
    prepare: async (page, baseURL) => {
      await apiSignIn(page, baseURL, "CLIENT", "Rahim Uddin");
      const projectId = await createOrderingProject(page, baseURL, { publish: true });
      const dev = await apiSignIn(page, baseURL, "DEVELOPER", "Nadia Rahman");
      await addSkillEvidence(page.request, baseURL, dev.userId, "React", 0.7);
      const taken = await addRoleResult(page.request, baseURL, dev.userId, projectId, "React");
      expect(taken.passed).toBe(true);
      await roleAnswerKey(page.request, taken.attempt_id); // the attempt exists and is readable
      return { path: `/dev/assessments/${taken.attempt_id}` };
    },
  },
  {
    // The admin's review queue (§12.1); it lists every role attempt of earlier runs too.
    name: "admin-assessments",
    randomContent: true,
    prepare: async (page, baseURL) => {
      await apiSignIn(page, baseURL, "ADMIN", "Admin User");
      return { path: "/admin/assessments?view=all" };
    },
  },
  {
    // A developer's public profile as a client sees it (§13.5 #9).
    name: "public-profile",
    prepare: async (page, baseURL) => {
      const dev = await apiSignIn(page, baseURL, "DEVELOPER", "Nadia Rahman");
      await page.goto("/dev/profile"); // the profile row is created on first open
      await page.getByLabel("Headline").waitFor();
      await apiSignIn(page, baseURL, "CLIENT", "Rahim Uddin");
      return { path: `/d/${dev.userId}` };
    },
  },
  {
    // The public list (§13.5 #6). The test database keeps every project earlier runs published,
    // so the plain list grows run by run; searching for one freshly published project's own
    // title gives the same single card every time.
    name: "public-projects",
    prepare: async (page, baseURL) => {
      await apiSignIn(page, baseURL, "CLIENT", "Rahim Uddin");
      const title = `Ordering system ${String(Date.now())}`;
      await createOrderingProject(page, baseURL, { publish: true, title });
      await page.request.post("/api/v1/auth/logout", {
        headers: await csrfHeaders(page.request, baseURL),
      });
      await page.context().clearCookies();
      return { path: `/projects?q=${encodeURIComponent(title)}` };
    },
    // The title carries the run's timestamp, so the card's heading differs every run.
    randomContent: true,
  },
  {
    // One public project, as a signed-out visitor sees it before signing in to bid (§13.5 #12).
    name: "public-project",
    prepare: async (page, baseURL) => {
      await apiSignIn(page, baseURL, "CLIENT", "Rahim Uddin");
      const id = await createOrderingProject(page, baseURL, { publish: true });
      // Sign out again: the screen is checked the way a visitor sees it.
      await page.request.post("/api/v1/auth/logout", {
        headers: await csrfHeaders(page.request, baseURL),
      });
      await page.context().clearCookies();
      return { path: `/p/${id}` };
    },
  },
  {
    // Team formation with a finished run (§13.5 #24): three bidders for a two-place React and
    // Testing team, one a qualified newcomer, the dial at 1, executed through the test-only
    // router (no worker). The team is exact-verified, so it is the same every run; the
    // convergence curve and the run's time are masked.
    name: "team-formation",
    prepare: async (page, baseURL) => {
      const { projectId } = await formedProject(page, baseURL);
      return { path: `/client/projects/${projectId}/formation` };
    },
  },
  {
    // "Why it wasn't selected" on a developer's own bid (§13.5 #12, §9.8).
    name: "bid-not-selected",
    prepare: async (page, baseURL) => {
      const { arif } = await formedProject(page, baseURL, true);
      await apiSignInAs(page, baseURL, arif);
      return { path: `/dev/bids/${arif.bidId}` };
    },
  },
  {
    // A selected developer's dashboard (§13.5 #9): the invitation banner with Accept and
    // Decline; the countdown is masked.
    name: "developer-invitation",
    prepare: async (page, baseURL) => {
      const { bidders } = await formedProject(page, baseURL, true);
      await apiSignInAs(page, baseURL, must(bidders, "Imran Kabir"));
      return { path: "/dev" };
    },
  },
  {
    // The client's Team screen (§13.5 #25) after the only Testing bidder declined: the
    // members with their states, and a repair with nobody to offer (the reasons, "Reopen place"
    // and nothing to rank). Countdowns are masked.
    name: "client-team-repair",
    prepare: async (page, baseURL) => {
      const { projectId, bidders } = await formedProject(page, baseURL, true);
      const client = await page.context().cookies();
      await apiSignInAs(page, baseURL, must(bidders, "Imran Kabir"));
      await post(
        page,
        baseURL,
        `/api/v1/invitations/${await invitationOf(page, projectId)}/decline`,
        {
          reason: "Booked on another project those weeks.",
        },
      );
      await page.context().clearCookies();
      await page.context().addCookies(client);
      const repair = (await (
        await page.request.get(`/api/v1/projects/${projectId}/repair`)
      ).json()) as { id: string };
      await post(page, baseURL, `/api/v1/__test__/repair-proposals/${repair.id}/execute`);
      return { path: `/client/projects/${projectId}/team` };
    },
  },
  {
    // The workspace's Team tab (§13.5 #33) of a started project, as a member sees it: no
    // prices, the lead badge, the other tabs marked for Phase 9.
    name: "workspace-team",
    prepare: async (page, baseURL) => {
      const { projectId, bidders } = await formedProject(page, baseURL, true);
      const client = await page.context().cookies();
      const team = (await (
        await page.request.get(`/api/v1/projects/${projectId}/team`)
      ).json()) as { members: { developer_name: string }[] };
      for (const m of team.members) {
        await apiSignInAs(page, baseURL, must(bidders, m.developer_name));
        await post(
          page,
          baseURL,
          `/api/v1/invitations/${await invitationOf(page, projectId)}/accept`,
        );
      }
      await page.context().clearCookies();
      await page.context().addCookies(client);
      const view = (await (
        await page.request.get(`/api/v1/projects/${projectId}/team`)
      ).json()) as { project_version: number; recommendation: { member_id: string } | null };
      const lead = await page.request.post(`/api/v1/projects/${projectId}/team/lead`, {
        headers: {
          ...(await csrfHeaders(page.request, baseURL)),
          "If-Match": String(view.project_version),
        },
        data: { member_id: view.recommendation?.member_id },
      });
      if (!lead.ok()) throw new Error(`lead → ${String(lead.status())} ${await lead.text()}`);
      const now = (await (await page.request.get(`/api/v1/projects/${projectId}/team`)).json()) as {
        project_version: number;
      };
      const start = await page.request.post(`/api/v1/projects/${projectId}/start`, {
        headers: {
          ...(await csrfHeaders(page.request, baseURL)),
          "If-Match": String(now.project_version),
        },
      });
      if (!start.ok()) throw new Error(`start → ${String(start.status())} ${await start.text()}`);
      await apiSignInAs(page, baseURL, must(bidders, "Sadia Islam"));
      return { path: `/w/${projectId}/team` };
    },
  },
];

function must(bidders: Map<string, Bidder>, name: string): Bidder {
  const b = bidders.get(name);
  if (!b) throw new Error(`no bid from ${name}`);
  return b;
}

/** The signed-in developer's pending invitation id for the project. */
async function invitationOf(page: Page, projectId: string): Promise<string> {
  const mine = (await (await page.request.get("/api/v1/me/invitations")).json()) as {
    invitations: { id: string; project_id: string; state: string }[];
  };
  const inv = mine.invitations.find((i) => i.project_id === projectId && i.state === "PENDING");
  if (!inv) throw new Error("no pending invitation");
  return inv.id;
}

interface Bidder {
  email: string;
  password: string;
  bidId: string;
}

async function post(page: Page, baseURL: string, path: string, data?: unknown): Promise<unknown> {
  const r = await page.request.post(path, {
    headers: await csrfHeaders(page.request, baseURL),
    data,
  });
  if (!r.ok()) throw new Error(`${path} → ${String(r.status())} ${await r.text()}`);
  return r.status() === 204 ? null : ((await r.json()) as unknown);
}

/** Sign a known account back in (the page's cookies are replaced). */
async function apiSignInAs(page: Page, baseURL: string, who: Bidder): Promise<void> {
  await page.context().clearCookies();
  const headers = await csrfHeaders(page.request, baseURL);
  const r = await throughAuthZone(() =>
    page.request.post("/api/v1/auth/login", {
      headers,
      data: { email: who.email, password: who.password, captcha: "test-bypass" },
    }),
  );
  if (!r.ok()) throw new Error(`login failed: ${String(r.status())} ${await r.text()}`);
}

/** A FORMING ordering project with bids from Nadia (newcomer, React), Arif (React) and Imran
 * (Testing), and FastAPI/PostgreSQL bids; a run at dial 1 executed, and (optionally) the team
 * confirmed with explanations written. Leaves the client signed in. */
async function formedProject(
  page: Page,
  baseURL: string,
  confirm = false,
): Promise<{ projectId: string; arif: Bidder; bidders: Map<string, Bidder> }> {
  await apiSignIn(page, baseURL, "CLIENT", "Rahim Uddin");
  const projectId = await createOrderingProject(page, baseURL, { publish: true });
  const client = page.context();
  const clientCookies = await client.cookies();
  const bids: [string, string, number, number, boolean][] = [
    ["Nadia Rahman", "React", 18_000, 20, true],
    ["Arif Hossain", "React", 26_000, 18, false],
    ["Tanvir Ahmed", "FastAPI", 25_000, 20, false],
    ["Sadia Islam", "PostgreSQL", 23_000, 21, false],
    ["Imran Kabir", "Testing", 20_000, 19, false],
  ];
  let arif: Bidder | null = null;
  const bidders = new Map<string, Bidder>();
  for (const [name, skill, price, days, newcomer] of bids) {
    await client.clearCookies();
    const dev = await apiSignIn(page, baseURL, "DEVELOPER", name);
    if (newcomer) {
      await addSkillEvidence(page.request, baseURL, dev.userId, skill, 0.9);
      await addRoleResult(page.request, baseURL, dev.userId, projectId, skill, "pass");
    } else {
      await addSkillEvidence(page.request, baseURL, dev.userId, skill, 0.8);
      await setReputation(page.request, baseURL, dev.userId, 0.8, 0.78);
    }
    const bid = (await post(page, baseURL, `/api/v1/projects/${projectId}/bids`, {
      slot_id: await slotFor(page.request, projectId, skill),
      price_paisa: price * 100,
      days_needed: days,
    })) as { id: string };
    const who = { email: dev.email, password: dev.password, bidId: bid.id };
    bidders.set(name, who);
    if (name === "Arif Hossain") arif = who;
  }
  await client.clearCookies();
  await client.addCookies(clientCookies);
  await post(page, baseURL, `/api/v1/__test__/projects/${projectId}/start-forming`);
  const run = (await post(page, baseURL, `/api/v1/projects/${projectId}/formation-runs`, {
    preset: "balanced",
    min_newcomers: 1,
  })) as { run_id: string };
  await post(page, baseURL, `/api/v1/__test__/formation-runs/${run.run_id}/execute`);
  if (confirm) {
    await post(page, baseURL, `/api/v1/formation-runs/${run.run_id}/confirm`);
    await post(page, baseURL, `/api/v1/__test__/formation-runs/${run.run_id}/explanations`);
  }
  if (!arif) throw new Error("no bid from Arif");
  return { projectId, arif, bidders };
}
