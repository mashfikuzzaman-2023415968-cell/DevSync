/**
 * Demo 1 walkthrough (spec §17.0), run by `make demo-check DEMO=1` on chromium, firefox, webkit
 * and a mobile viewport, three times, with video. One page drives the whole story, switching
 * people by signing in, so the video is a single take:
 *
 * landing page → a client registers and verifies phone (OTP) and email → an admin signs in with
 * TOTP → the client plans a 6-milestone project in the wizard (CPM: critical path and Frontend's
 * slack; a circular dependency is rejected) and publishes it → a newcomer completes a profile and
 * passes the timed React test → developers search and filter projects and place sealed bids, one
 * of which "would be filtered out" → a second developer can't see the first one's bid → the
 * client sees every bid with its eligibility and reasons, and the too-few-bids banner → the
 * seeded "Online ordering system" (§18.4) shows all 12 bids with the documented reasons.
 *
 * Runs against the test stack (DEVSYNC_ENV=test): codes, links, TOTP and the skill test's answer
 * key come from the test-only router (e2e/fixtures.ts). The seeded part signs in as Rahim with
 * `DEMO_PASSWORD`, which demo_check.py generates and passes to both the seed and this run.
 *
 * Every step is captured (full page, CSS pixels) to
 * `test-results/demo-1-shots/<project>/r<repeat>/NN-step.png`, plus a dark-mode twin on the
 * first repeat; `steps.json` lists them in order with a caption for the report and gallery.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { Page, TestInfo } from "@playwright/test";
import { closeDialog, expect, optionChosen, test } from "../test";
import {
  addRoleResult,
  addSkillEvidence,
  apiSignIn,
  csrfHeaders,
  lastLink,
  lastSms,
  PASSWORD,
  seedUser,
  signIn,
  takeRoleAssessment,
  totpNow,
  uniqueEmail,
  uniquePhone,
} from "../fixtures";

test.use({ video: { mode: "on", size: { width: 1280, height: 720 } } });

const TITLE = "Cafe ordering system";
const ORDERING = "Online ordering system";
// §18.2: name, days, share %, predecessors.
const PLAN: [string, number, number, string[]][] = [
  ["Requirements & design", 4, 10, []],
  ["Database", 5, 15, ["Requirements & design"]],
  ["Backend API", 8, 25, ["Database"]],
  ["Frontend", 9, 20, ["Requirements & design"]],
  ["Integration", 3, 10, ["Backend API", "Frontend"]],
  ["Testing & launch", 4, 20, ["Integration"]],
];
const SLOTS = ["React", "FastAPI", "PostgreSQL", "Testing"];

interface Step {
  file: string;
  dark: string | null;
  caption: string;
}

/** Screenshots of every step, in a stable folder the readiness report links to. */
class Shots {
  private readonly dir: string;
  private readonly steps: Step[] = [];
  private n = 0;

  constructor(
    private readonly page: Page,
    private readonly info: TestInfo,
  ) {
    this.dir = join(
      info.project.outputDir,
      "demo-1-shots",
      info.project.name,
      `r${String(info.repeatEachIndex)}`,
    );
    mkdirSync(this.dir, { recursive: true });
  }

  async take(name: string, caption: string): Promise<void> {
    this.n += 1;
    const base = `${String(this.n).padStart(2, "0")}-${name}`;
    await settle(this.page);
    // CSS scale: a phone at 3× density would exceed the 32,767 px screenshot limit on long pages.
    await this.page.screenshot({
      path: join(this.dir, `${base}.png`),
      fullPage: true,
      scale: "css",
    });
    let dark: string | null = null;
    if (this.info.repeatEachIndex === 0) {
      await this.page.emulateMedia({ colorScheme: "dark" });
      await settle(this.page);
      dark = `${base}-dark.png`;
      await this.page.screenshot({ path: join(this.dir, dark), fullPage: true, scale: "css" });
      await this.page.emulateMedia({ colorScheme: "light" });
      await settle(this.page);
    }
    this.steps.push({ file: `${base}.png`, dark, caption });
    writeFileSync(join(this.dir, "steps.json"), JSON.stringify(this.steps, null, 2));
  }
}

/** Wait for finite animations and transitions (e.g. a theme change) to finish, then a frame. */
async function settle(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const finite = document
      .getAnimations()
      .filter((a) => Number.isFinite(Number(a.effect?.getComputedTiming().endTime ?? Infinity)));
    await Promise.all(finite.map((a) => a.finished.catch(() => undefined)));
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          resolve();
        });
      }),
    );
  });
}

/** Sign the page's browser context in through the API (password only; not for admins). */
async function apiLogin(page: Page, baseURL: string, email: string, password: string) {
  const r = await page.request.post("/api/v1/auth/login", {
    headers: await csrfHeaders(page.request, baseURL),
    data: { email, password, captcha: "test-bypass" },
  });
  if (!r.ok()) throw new Error(`login ${email} → ${String(r.status())} ${await r.text()}`);
}

/** Become someone else: drop the current session, then sign in as them. */
async function switchTo(page: Page, baseURL: string, email: string, password: string) {
  await page.context().clearCookies();
  await apiLogin(page, baseURL, email, password);
}

async function fillChecked(page: Page, label: RegExp, value: string): Promise<void> {
  // Fill and confirm (Firefox once dropped a fill that raced the form's first render).
  const field = page.getByLabel(label);
  await expect(async () => {
    await field.fill(value);
    await expect(field).toHaveValue(value, { timeout: 1000 });
  }).toPass({ timeout: 10_000 });
}

async function fillBid(page: Page, skill: string, price: string, days: string): Promise<void> {
  await page.getByRole("combobox").click();
  await page.getByRole("option", { name: skill }).first().click();
  await optionChosen(page);
  await fillChecked(page, /Your price/, price);
  await fillChecked(page, /Days you need/, days);
}

function milestoneRow(page: Page, index: number) {
  return page.locator("li", { has: page.getByLabel("Name", { exact: true }) }).nth(index);
}

async function next(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Continue" }).click();
}

test("Demo 1 — accounts, planning, profiles, sealed bidding and filtering @demo", async ({
  page,
  baseURL,
}, info) => {
  test.setTimeout(600_000);
  const base = baseURL ?? "";
  const shots = new Shots(page, info);

  // 1. Landing page.
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await shots.take("landing", "Landing page");

  // 2. A client registers, then verifies the phone (OTP) and the email (link).
  const client = { email: uniqueEmail("demo-client"), phone: uniquePhone() };
  await page.goto("/register?role=client");
  await page.getByLabel("Full name").fill("Sumaiya Haque");
  await page.getByLabel("Email").fill(client.email);
  await page.getByLabel("Mobile number").fill(client.phone);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByLabel(/I agree to the terms/).check();
  await shots.take("register", "A client registers");
  // Public forms reject submissions made under 2 s after the page opened (bot check, §14.16).
  await page.waitForTimeout(2100);
  await page.getByRole("button", { name: /Create account|Checking/ }).click();
  await expect(page).toHaveURL(/\/verify$/);
  const code = await lastSms(page.request, client.phone);
  expect(code).toMatch(/^\d{6}$/);
  await page.getByLabel("Digit 1 of 6").fill(code.charAt(0));
  await page.keyboard.type(code.slice(1));
  await shots.take("verify-phone", "The client types the code sent to their phone");
  await page.getByRole("button", { name: "Verify phone" }).click();
  await expect(page.getByText("✓ Phone verified")).toBeVisible();
  const link = new URL(await lastLink(page.request, client.email, "verify_email"));
  await page.goto(link.pathname + link.search);
  await expect(page.getByText("Your email is verified.")).toBeVisible();
  await shots.take("verify-email", "The emailed link verifies the address");
  await page.getByRole("link", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/client$/);

  // 3. An administrator signs in with a password and a TOTP code.
  await page.context().clearCookies();
  const admin = await seedUser(page.request, base, "ADMIN", "Administrator");
  await signIn(page, admin.email, admin.password);
  await expect(page).toHaveURL(/\/login\/totp$/);
  const totp = await totpNow(page.request, admin.totpSecret ?? "");
  await page.getByLabel("Digit 1 of 6").fill(totp.charAt(0));
  await page.keyboard.type(totp.slice(1));
  await shots.take("admin-totp", "The admin confirms sign-in with an authenticator code");
  await page.getByRole("button", { name: "Verify and sign in" }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole("heading", { name: "Administration" })).toBeVisible();
  await shots.take("admin-home", "Admin area (TOTP required)");

  // 4. The client plans the §18.2 project in the wizard.
  await switchTo(page, base, client.email, PASSWORD);
  await page.goto("/client/projects/new");
  await page.getByLabel("Project title").fill(TITLE);
  await page.getByLabel("One-line summary").fill("Customers order online; staff track orders.");
  await next(page);
  await page
    .getByLabel("Requirements", { exact: true })
    .fill("Ordering, payments (simulated), order tracking.");
  await page.getByLabel("Deadline (days)").fill("30");
  await next(page);
  for (let i = 1; i < SLOTS.length; i += 1) {
    await page.getByRole("button", { name: "Add slot" }).click();
  }
  for (const [i, skill] of SLOTS.entries()) {
    await page.getByRole("combobox").nth(i).click();
    await page.getByRole("option", { name: skill, exact: true }).click();
    await optionChosen(page);
  }
  await expect(page.getByText("Team size:")).toContainText("4");
  await shots.take("wizard-team", "Wizard: four skill slots, a team of four");
  await next(page);
  await expect(page.getByText("Plan preview")).toBeVisible();
  for (let i = 1; i < PLAN.length; i += 1) {
    await page.getByRole("button", { name: "Add milestone" }).click();
  }
  for (const [i, [name, days, share]] of PLAN.entries()) {
    const row = milestoneRow(page, i);
    await row.getByLabel("Name", { exact: true }).fill(name);
    await row.getByLabel("Days", { exact: true }).fill(String(days));
    await row.getByLabel("Share %", { exact: true }).fill(String(share));
  }
  for (const [i, [, , , preds]] of PLAN.entries()) {
    for (const pred of preds) {
      await milestoneRow(page, i).getByRole("button", { name: pred, exact: true }).click();
    }
  }
  await expect(page.getByText("Share total 100%")).toBeVisible();
  await expect(page.getByText("Duration 24 days")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("5 critical milestones")).toBeVisible();
  await expect(page.getByLabel("Frontend: days 4–13, slack 4 days")).toBeVisible();
  await expect(page.getByLabel("Backend API: days 9–17, on the critical path")).toBeVisible();
  await shots.take("wizard-cpm", "CPM timeline: 24 days, critical path, Frontend has 4 days slack");

  // A circular dependency is shown and blocks Continue; removing it restores the plan.
  const first = milestoneRow(page, 0);
  await first.getByRole("button", { name: "Testing & launch", exact: true }).click();
  await expect(page.getByText(/depend on each other in a loop/i)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("button", { name: "Continue" })).toBeDisabled();
  await shots.take("wizard-cycle", "A circular dependency is rejected");
  await first.getByRole("button", { name: "Testing & launch", exact: true }).click();
  await expect(page.getByText("Duration 24 days")).toBeVisible({ timeout: 10_000 });
  await next(page);
  await page.getByLabel("Budget (৳)").fill("120000");
  await next(page);
  await expect(page.getByText("Review and publish")).toBeVisible();
  const publish = page.getByRole("button", { name: "Publish for bidding" });
  await page.getByRole("button", { name: "Verify payment method" }).click();
  await expect(page.getByText("Payment method verified").first()).toBeVisible();
  await expect(publish).toBeEnabled();
  await shots.take("wizard-review", "Review: payment method verified, ready to publish");
  await publish.click();
  await expect(page).toHaveURL(/\/client\/projects\/[0-9a-f-]+\/plan$/, { timeout: 15_000 });
  const projectId = page.url().split("/")[5] ?? "";
  await expect(page.getByLabel("Frontend: days 4–13, slack 4 days")).toBeVisible();
  await shots.take("plan", "The published plan (Gantt with the critical path)");

  // 5. A newcomer completes a profile and takes the timed React practice test.
  await page.context().clearCookies();
  const newcomer = await apiSignIn(page, base, "DEVELOPER", "Tania Sultana");
  await page.goto("/dev/profile");
  await expect(page.locator(".skeleton")).toHaveCount(0);
  await page.getByLabel("Headline").fill("React developer, new to DevSync");
  await expect(page.getByText("Saved", { exact: true })).toBeVisible({ timeout: 10_000 });
  await page.getByRole("checkbox", { name: "React" }).click();
  await expect(page.getByRole("radiogroup", { name: "React level" })).toBeVisible();
  await page.getByRole("button", { name: "Add a portfolio item" }).click();
  const add = page.getByRole("dialog", { name: "Add a portfolio item" });
  await add.getByLabel("Title").fill("Recipe sharing app");
  await add.getByRole("button", { name: "Add item" }).click();
  const edit = page.getByRole("dialog", { name: "Edit portfolio item" });
  await expect(edit).toBeVisible();
  await edit.getByRole("button", { name: "Close" }).first().click();
  await expect(edit).toBeHidden();
  await shots.take("profile", "A newcomer completes their profile");

  await page.goto("/dev/challenges");
  await page
    .getByRole("group", { name: "React skill test" })
    .getByRole("button", { name: "Start test" })
    .click();
  await page.getByRole("button", { name: "Start the timer" }).click();
  await expect(page).toHaveURL(/\/dev\/challenges\/test\/[0-9a-f-]+/, { timeout: 15_000 });
  await expect(page.getByText("Question 1 of 10")).toBeVisible();
  const attemptId = new URL(page.url()).pathname.split("/").pop() ?? "";
  const keyResponse = await page.request.get(`/api/v1/__test__/attempts/${attemptId}/answer-key`);
  expect(keyResponse.ok()).toBe(true);
  const { answers } = (await keyResponse.json()) as { answers: number[] };
  expect(answers).toHaveLength(10);
  await shots.take("skill-test", "The timed React practice test (server-side timer)");
  for (const [i, choice] of answers.entries()) {
    await page.getByRole("radio").nth(choice).click();
    await expect(
      page.getByRole("progressbar", { name: `${String(i + 1)} of 10 answered` }),
    ).toBeVisible();
    if (i < answers.length - 1) await page.getByRole("button", { name: "Next question" }).click();
  }
  await page.getByRole("button", { name: "Submit test" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Submit test" }).click();
  await expect(page.getByText(/10 of 10 correct/)).toBeVisible();
  await expect(page.getByText("Added to your profile as a practice result.")).toBeVisible();
  await shots.take("skill-test-passed", "The practice result is added to the profile");

  // 6. The newcomer searches and filters projects, then places a sealed bid.
  await page.goto("/dev/find");
  await page.getByLabel("Search projects", { exact: true }).fill("cafe");
  await page.getByLabel("Max deadline (days)").fill("30");
  await expect(page).toHaveURL(/q=cafe/);
  await expect(page).toHaveURL(/deadline_max=30/);
  await expect(page.getByRole("link", { name: new RegExp(TITLE) }).first()).toBeVisible();
  await shots.take("find-work", "Search and filter open projects");
  await page.goto(`/dev/projects/${projectId}`);
  await expect(page.getByRole("heading", { name: TITLE })).toBeVisible();
  await fillBid(page, "React", "18000", "20");
  // A newcomer bids on a role assessment for this role, not on the practice test (§14.2).
  await expect(page.getByText("Role assessment required")).toBeVisible({ timeout: 10_000 });
  await shots.take("assessment-required", "Newcomers take a role assessment for this role");
  // Tania's assessment is taken off screen here; Rafsan takes one live in step 10.
  await addRoleResult(page.request, base, newcomer.userId, projectId, "React", "pass");
  await page.reload();
  await fillBid(page, "React", "18000", "20");
  await expect(page.getByText(/Role assessment passed/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/meet every requirement/i)).toBeVisible({ timeout: 10_000 });
  await shots.take("bid-eligible", "Live eligibility preview: the newcomer qualifies");
  await page.getByRole("button", { name: "Place sealed bid" }).click();
  await expect(page.getByText("Bid placed").first()).toBeVisible();

  // 7. A second developer can't see that bid, and their own would be filtered out.
  await page.context().clearCookies();
  const second = await apiSignIn(page, base, "DEVELOPER", "Farid Ahmed");
  await addSkillEvidence(page.request, base, second.userId, "React", 0.9);
  await addRoleResult(page.request, base, second.userId, projectId, "React", "pass");
  await page.goto("/dev/bids");
  await expect(page.getByText("No bids yet")).toBeVisible();
  await page.goto(`/dev/projects/${projectId}`);
  await expect(page.getByRole("button", { name: "Place sealed bid" })).toBeVisible();
  await expect(page.getByText(/18,000/)).toHaveCount(0);
  await shots.take("sealed", "Another developer sees nothing of the first bid (sealed)");
  await fillBid(page, "React", "20000", "45");
  await expect(page.getByText(/would be filtered out/i)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/more days than the deadline allows/i)).toBeVisible();
  await shots.take("bid-filtered", "“Would be filtered out because…” before bidding");
  await page.getByRole("button", { name: "Place sealed bid" }).click();
  await expect(page.getByText("Bid placed").first()).toBeVisible();
  expect(newcomer.userId).not.toBe(second.userId);

  // 8. The client sees every bid with its eligibility, and the too-few-bids banner.
  await switchTo(page, base, client.email, PASSWORD);
  await page.goto(`/client/projects/${projectId}/bids`);
  const visible = (text: string | RegExp) => page.getByText(text).filter({ visible: true }).first();
  await expect(visible("Tania Sultana")).toBeVisible();
  await expect(visible("Farid Ahmed")).toBeVisible();
  await expect(visible("Can’t meet the deadline")).toBeVisible();
  await expect(page.getByText(/2 bids, 1 eligible/)).toBeVisible();
  await expect(page.getByText("Not enough eligible bids yet")).toBeVisible();
  await shots.take("client-bids", "The client sees both bids, reasons and the too-few banner");
  await page
    .getByRole("button", { name: "Why eligible: Tania Sultana" })
    .filter({ visible: true })
    .click();
  await expect(
    page
      .getByRole("dialog", { name: "Tania Sultana" })
      .getByText(/newcomer rule: passed the role assessment/),
  ).toBeVisible();
  await shots.take("why-newcomer", "Why eligible: the newcomer rule, check by check");
  await closeDialog(page, "Tania Sultana");
  await page.getByRole("button", { name: "Fix the shortfall" }).click();
  await expect(page.getByRole("dialog", { name: "Fix the shortfall" })).toBeVisible();
  await shots.take("fix-shortfall", "Fixing the shortfall: lower standards, budget, team, extend");
  await closeDialog(page, "Fix the shortfall");

  // 9. The seeded marketplace (§18.4): all 12 bids with the documented reasons.
  const demoPassword = process.env.DEMO_PASSWORD ?? "";
  if (!demoPassword) {
    throw new Error("DEMO_PASSWORD is not set: run through `make demo-check DEMO=1`");
  }
  await switchTo(page, base, "rahim@devsync.local", demoPassword);
  await page.goto("/client/projects");
  const row = page.getByRole("link", { name: ORDERING }).first();
  await expect(row).toBeVisible();
  const seededId = ((await row.getAttribute("href")) ?? "").split("/")[3] ?? "";
  await page.goto(`/client/projects/${seededId}/bids`);
  await expect(page.getByText(/12 bids, 10 eligible/)).toBeVisible();
  await expect(visible("Can’t meet the deadline")).toBeVisible();
  await expect(visible("No passing role assessment")).toBeVisible();
  await shots.take("seeded-bids", "Seeded project: 12 sealed bids, 10 eligible, 2 reasons");
  await page
    .getByRole("button", { name: "Why not eligible: Lamia Akter" })
    .filter({ visible: true })
    .click();
  await expect(
    page
      .getByRole("dialog", { name: "Lamia Akter" })
      .getByText(/below the pass mark of 60/)
      .first(), // the summary line and the step that failed both say it
  ).toBeVisible();
  await shots.take("why-failed-assessment", "Lamia failed her FastAPI role assessment");
  await closeDialog(page, "Lamia Akter");

  // 10. A newcomer takes the React role assessment live and bids (role assessment spec §14.2).
  // A fresh "Rafsan Haque" each run: the seeded Rafsan stays untouched for the presenter, and
  // the bid is withdrawn at the end so the seeded project keeps its documented 12 bids.
  await page.context().clearCookies();
  const rafsan = await apiSignIn(page, base, "DEVELOPER", "Rafsan Haque");
  await addSkillEvidence(page.request, base, rafsan.userId, "React", 0.7);
  await page.goto(`/dev/projects/${seededId}`);
  await expect(page.getByRole("heading", { name: ORDERING })).toBeVisible();
  await fillBid(page, "React", "16000", "20");
  await fillChecked(page, /Hours a week/, "20");
  await page.getByLabel("Proposal").fill("React screens for the menu, cart and order tracking.");
  await expect(page.getByText("Role assessment required")).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "Why these?" }).click();
  await shots.take("rafsan-required", "The role assessment: competencies, weights and why");
  await takeRoleAssessment(page, { shot: (name, caption) => shots.take(name, caption) });
  await page.getByRole("button", { name: "Back to your bid" }).click();
  // The draft is intact after the assessment.
  await expect(page.getByLabel(/Your price/)).toHaveValue("16000");
  await expect(page.getByText(/Role assessment passed/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/meet every requirement/i)).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "Place sealed bid" }).click();
  await expect(page.getByText("Bid placed").first()).toBeVisible();

  // 11. The client sees the assessment line on Rafsan's bid.
  await switchTo(page, base, "rahim@devsync.local", demoPassword);
  await page.goto(`/client/projects/${seededId}/bids`);
  await page
    .getByRole("button", { name: "Why eligible: Rafsan Haque" })
    .filter({ visible: true })
    .click();
  const why = page.getByRole("dialog", { name: "Rafsan Haque" });
  await expect(why.getByTestId("assessment-line")).toContainText(/Role assessment: \d+, passed/);
  await shots.take("client-assessment-line", "The client sees the result, never the answers");
  await closeDialog(page, "Rafsan Haque");

  // Leave the seeded project as it was (12 standing bids) for the next run.
  await switchTo(page, base, rafsan.email, PASSWORD);
  await page.goto(`/dev/projects/${seededId}`);
  await page.getByRole("button", { name: "Withdraw bid" }).click();
  await expect(page.getByText("Bid withdrawn").first()).toBeVisible();
});
