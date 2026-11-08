/**
 * Role assessment end to end (role assessment spec §17.6), on every browser the gate runs
 * (Chromium, Firefox, WebKit, iPhone 14 — the last two use the focus layout where full screen
 * isn't available). The happy path (take it, pass, bid, the client's line) is in the Demo 1
 * walkthrough; this file covers the rules around it.
 *
 * Leaving is simulated by flipping `document.visibilityState` and dispatching the event the
 * browser would, the same signal a tab switch, minimise or reload gives the focus guard.
 * Expiry (time running out) is covered by the backend API tests, which move an attempt's
 * deadline through the database: the shortest time limit a setting allows is five minutes.
 */
import type { Page } from "@playwright/test";
import { expect, noSmoothScroll, optionChosen, test } from "./test";

/** Eight letters from the clock (display names allow letters, not digits). */
function uniqueLetters(): string {
  return Date.now()
    .toString(26)
    .slice(-8)
    .replace(/[0-9]/g, (d) => "qrstuvwxyz"[Number(d)] ?? "q")
    .replace(/^./, (c) => c.toUpperCase());
}
import {
  addSkillEvidence,
  apiSignIn,
  createOrderingProject,
  roleAnswerKey,
  setReputation,
  takeRoleAssessment,
} from "./fixtures";

async function openSlot(page: Page, projectId: string, skill = "React"): Promise<void> {
  await page.goto(`/dev/projects/${projectId}`);
  await page.getByRole("combobox").click();
  await page.getByRole("option", { name: skill }).first().click();
  await optionChosen(page);
}

async function leave(page: Page): Promise<void> {
  await page.evaluate(() => {
    const set = (value: string) => {
      Object.defineProperty(document, "visibilityState", { configurable: true, value });
      document.dispatchEvent(new Event("visibilitychange"));
    };
    set("hidden");
    set("visible");
  });
}

async function startAssessment(page: Page): Promise<string> {
  await page.getByRole("button", { name: "Start assessment" }).click();
  const consent = page.getByRole("dialog", { name: "Before you start" });
  await consent.getByRole("checkbox", { name: "I understand and agree" }).click();
  const started = page.waitForResponse(
    (r) => r.url().includes("/assessment/attempts") && r.request().method() === "POST",
  );
  await consent.getByRole("button", { name: "Start assessment" }).click();
  const attempt = (await (await started).json()) as { id: string };
  await expect(page.getByTestId("assessment-runner").getByText("Question 1 of 12")).toBeVisible();
  return attempt.id;
}

async function answerNext(page: Page, choice: number, number: number): Promise<void> {
  const runner = page.getByTestId("assessment-runner");
  await expect(runner.getByText(`Question ${String(number)} of 12`)).toBeVisible();
  await runner.getByRole("radio").nth(choice).click();
  await runner.getByRole("button", { name: "Confirm answer" }).click();
}

test("a failed assessment locks the retake and keeps the bid closed @e2e", async ({
  page,
  baseURL,
}) => {
  const base = baseURL ?? "";
  await apiSignIn(page, base, "CLIENT", "Rahim");
  const projectId = await createOrderingProject(page, base, { publish: true });
  const dev = await apiSignIn(page, base, "DEVELOPER", "Sumaiya Akter");
  await addSkillEvidence(page.request, base, dev.userId, "React", 0.7);
  await openSlot(page, projectId);
  await expect(page.getByText("Role assessment required")).toBeVisible();
  await takeRoleAssessment(page, { choose: (_i, correct) => (correct + 1) % 4 });
  await expect(page.getByRole("heading", { name: /Not passed/ })).toBeVisible();
  await expect(page.getByText(/You can retake this assessment on/)).toBeVisible();
  await page.getByRole("button", { name: "Back to your bid" }).click();
  await expect(page.getByText(/not passed/).first()).toBeVisible();
  await expect(page.getByText(/You can retake it on/)).toBeVisible();
  await page.getByLabel(/Your price/).fill("16000");
  await page.getByLabel(/Days you need/).fill("20");
  await expect(page.getByRole("button", { name: "Place sealed bid" })).toBeDisabled();
});

test("leaving twice ends the attempt, and the admin sees it flagged @e2e", async ({
  page,
  browser,
  baseURL,
}) => {
  const base = baseURL ?? "";
  await apiSignIn(page, base, "CLIENT", "Rahim");
  const projectId = await createOrderingProject(page, base, { publish: true });
  // The admin queue keeps attempts from earlier runs, so this run's developer gets its own name.
  const name = `Imtiaz ${uniqueLetters()}`;
  const dev = await apiSignIn(page, base, "DEVELOPER", name);
  await addSkillEvidence(page.request, base, dev.userId, "React", 0.7);
  await openSlot(page, projectId);
  const attemptId = await startAssessment(page);
  await answerNext(page, 0, 1);
  await leave(page);
  const warning = page.getByRole("alertdialog", { name: "You left the assessment" });
  await expect(warning).toBeVisible();
  await expect(warning.getByText(/only warning/)).toBeVisible();
  await warning
    .getByRole("button", { name: /Return to full screen|Continue without full screen/ })
    .click();
  // A second, separate leave (more than 5 s later; closer signals count as the same leave).
  await page.waitForTimeout(5500);
  await leave(page);
  await expect(page.getByRole("heading", { name: /Ended early/ })).toBeVisible();
  await expect(page.getByText(/can’t count as a pass/)).toBeVisible();

  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, baseURL: base });
  const admin = await ctx.newPage();
  await noSmoothScroll(admin); // older flagged attempts can push this row below the fold
  await apiSignIn(admin, base, "ADMIN", "Administrator");
  await admin.goto("/admin/assessments");
  const row = admin.getByRole("listitem").filter({ hasText: name });
  await expect(row).toBeVisible();
  await expect(row.getByText("Ended (left twice)")).toBeVisible();
  const open = row.getByRole("link", { name: "Open" });
  await expect(open).toHaveAttribute("href", `/admin/assessments/${attemptId}`);
  await open.click();
  await admin.waitForURL((url) => url.pathname === `/admin/assessments/${attemptId}`);
  await expect(admin.getByRole("heading", { name: "Focus events" })).toBeVisible({
    timeout: 15_000,
  });
  await expect(admin.getByText("visibility hidden").first()).toBeVisible();
  await ctx.close();
});

test("a short loss of focus isn't a leave @e2e", async ({ page, baseURL }) => {
  const base = baseURL ?? "";
  await apiSignIn(page, base, "CLIENT", "Rahim");
  const projectId = await createOrderingProject(page, base, { publish: true });
  const dev = await apiSignIn(page, base, "DEVELOPER", "Nabila Notification");
  await addSkillEvidence(page.request, base, dev.userId, "React", 0.7);
  await openSlot(page, projectId);
  await startAssessment(page);
  await page.evaluate(() => {
    window.dispatchEvent(new Event("blur"));
    setTimeout(() => window.dispatchEvent(new Event("focus")), 500);
  });
  await page.waitForTimeout(4000);
  await expect(page.getByRole("alertdialog", { name: "You left the assessment" })).toHaveCount(0);
  await expect(page.getByText("(1 warning left)")).toBeVisible();
});

test("a reload counts one leave and resumes at the same question @e2e", async ({
  page,
  baseURL,
}) => {
  const base = baseURL ?? "";
  await apiSignIn(page, base, "CLIENT", "Rahim");
  const projectId = await createOrderingProject(page, base, { publish: true });
  const dev = await apiSignIn(page, base, "DEVELOPER", "Rehana Reloads");
  await addSkillEvidence(page.request, base, dev.userId, "React", 0.7);
  await openSlot(page, projectId);
  const attemptId = await startAssessment(page);
  const key = await roleAnswerKey(page.request, attemptId);
  await answerNext(page, key[0]?.answer ?? 0, 1);
  await answerNext(page, key[1]?.answer ?? 0, 2);
  // The answer is saved once the next question shows; a reload before that cancels the request.
  await expect(page.getByTestId("assessment-runner").getByText("Question 3 of 12")).toBeVisible();
  await page.reload();
  await openSlot(page, projectId);
  await expect(page.getByText("Your assessment for this role is in progress.")).toBeVisible();
  await page.getByRole("button", { name: "Resume assessment" }).click();
  const runner = page.getByTestId("assessment-runner");
  await expect(runner.getByText("Question 3 of 12")).toBeVisible();
  await expect(runner.getByText("(no warnings left)")).toBeVisible(); // the reload was a leave
});

test("opening the attempt in another window stops this one @e2e", async ({ page, baseURL }) => {
  const base = baseURL ?? "";
  await apiSignIn(page, base, "CLIENT", "Rahim");
  const projectId = await createOrderingProject(page, base, { publish: true });
  const dev = await apiSignIn(page, base, "DEVELOPER", "Wahid Two Windows");
  await addSkillEvidence(page.request, base, dev.userId, "React", 0.7);
  await openSlot(page, projectId);
  const attemptId = await startAssessment(page);
  const other = await page.context().newPage();
  // The test waits for the button below, so it need not also wait for every asset's load event
  // (a second Firefox tab under a loaded machine could sit on it for the whole timeout).
  await other.goto(`/dev/assessments/${attemptId}`, { waitUntil: "domcontentloaded" });
  await expect(other.getByRole("button", { name: "Continue assessment" })).toBeVisible();
  await answerNext(page, 0, 1);
  await expect(
    page.getByRole("heading", { name: "This assessment continued in another window" }),
  ).toBeVisible();
  await other.close();
});

test("a pass counts for another project with the same role, and experienced developers skip it @e2e", async ({
  page,
  baseURL,
}) => {
  const base = baseURL ?? "";
  await apiSignIn(page, base, "CLIENT", "Rahim");
  const first = await createOrderingProject(page, base, { publish: true });
  const second = await createOrderingProject(page, base, { publish: true });
  // Two projects take ~10 CSRF fetches under /api/v1/auth/; let Nginx's auth zone (5 r/s,
  // burst 10, which the test reset can't clear) refill before signing in again.
  await page.waitForTimeout(2500);
  const dev = await apiSignIn(page, base, "DEVELOPER", "Rina Reuses");
  await addSkillEvidence(page.request, base, dev.userId, "React", 0.7);
  await openSlot(page, first);
  await takeRoleAssessment(page);
  await expect(page.getByRole("heading", { name: /Passed/ })).toBeVisible();
  await page.getByRole("button", { name: "Back to your bid" }).click();
  // Same requirements → same blueprint fingerprint → already passed (§6.7).
  await openSlot(page, second);
  await expect(page.getByText(/Role assessment passed/)).toBeVisible();

  const pro = await apiSignIn(page, base, "DEVELOPER", "Arif Hossain");
  await addSkillEvidence(page.request, base, pro.userId, "React", 0.9);
  await setReputation(page.request, base, pro.userId, 0.8, 0.75);
  await openSlot(page, first);
  await page.getByLabel(/Your price/).fill("18000");
  await page.getByLabel(/Days you need/).fill("20");
  await expect(page.getByText(/meet every requirement/i)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Role assessment required")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Place sealed bid" })).toBeEnabled();
});
