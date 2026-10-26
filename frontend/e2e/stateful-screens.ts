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
import type { Page } from "@playwright/test";
import {
  apiSignIn,
  createOrderingProject,
  csrfHeaders,
  lastLink,
  PASSWORD,
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
    // The timed skill test, with the countdown running and the first question shown.
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
