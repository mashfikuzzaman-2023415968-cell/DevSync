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
  addRoleResult,
  addSkillEvidence,
  apiSignIn,
  createOrderingProject,
  csrfHeaders,
  lastLink,
  PASSWORD,
  roleAnswerKey,
  seedUser,
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
}

export const STATEFUL_SCREENS: StatefulScreen[] = [
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
    // The full-screen runner on its first question (§11.3); questions are drawn per attempt.
    name: "assessment-runner",
    randomContent: true,
    prepare: async (page, baseURL) => {
      const path = await newcomerOnBidSheet(page, baseURL, "Nadia Rahman");
      await openConsent(page, path);
      const consent = page.getByRole("dialog", { name: "Before you start" });
      await consent.getByRole("checkbox", { name: "I understand and agree" }).click();
      await consent.getByRole("button", { name: "Start assessment" }).click();
      await page.getByTestId("assessment-runner").getByText("Question 1 of 12").waitFor();
      return {
        open: async (p) => {
          await p.goto(path);
          await p.getByRole("button", { name: "Resume assessment" }).click();
          await p
            .getByTestId("assessment-runner")
            .getByText(/Question \d+ of 12/)
            .waitFor();
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
];
