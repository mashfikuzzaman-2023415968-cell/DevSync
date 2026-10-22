/**
 * Demo 1 walkthrough (spec §17.0), run by `make demo-check DEMO=1` on chromium, firefox, webkit
 * and a mobile viewport (three times) to produce rehearsal screenshots and a report. It drives
 * the **seeded** Stage-1 data (`make seed-demo STAGE=1`), so it shows the real documented bids:
 * the client sees all 12 with eligibility and the two ineligible reasons, opens "Why?" on the
 * newcomer's bid (the newcomer rule, check by check), the too-few-bids banner and its "Fix the
 * shortfall" dialog appear on the short project (opened, nothing applied, so repeats see the same
 * seed), and a newcomer sees the live eligibility preview on the short project's bid sheet.
 *
 * Login uses the seeded demo accounts (printed by the seed). Registration, email/OTP verification
 * and admin TOTP are shown live in the demo and covered by the Phase 1 E2E; this spec focuses on
 * the Phase 4–5 highlights (the CPM plan and sealed bidding with Algorithm 1 filtering).
 */
import type { Page, TestInfo } from "@playwright/test";
import { closeDialog, expect, test } from "../test";
import { csrfHeaders } from "../fixtures";

const PW = "demo password strong 1!";
const ORDERING = "Online ordering system";

async function loginSeeded(page: Page, baseURL: string, email: string): Promise<void> {
  const r = await page.request.post("/api/v1/auth/login", {
    headers: await csrfHeaders(page.request, baseURL),
    data: { email, password: PW, captcha: "test-bypass" },
  });
  if (!r.ok()) throw new Error(`login ${email} → ${String(r.status())} ${await r.text()}`);
}

async function shot(page: Page, info: TestInfo, name: string): Promise<void> {
  // CSS scale: a phone at 3× density would exceed the 32,767 px screenshot limit on long pages.
  await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true, scale: "css" });
}

test("Demo 1 — planning, sealed bidding and Algorithm 1 filtering @demo", async ({
  page,
  baseURL,
}, info) => {
  // The whole Demo 1 story in one test, with full-page screenshots at every step.
  test.setTimeout(180_000);
  const url = baseURL ?? "";

  // 1. Landing page.
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await shot(page, info, "01-landing");

  // 2. The client sees every bid on the ordering project with eligibility + reasons.
  await loginSeeded(page, url, "rahim@devsync.local");
  await page.goto("/client/projects");
  await expect(page.getByText(ORDERING)).toBeVisible();
  const row = page.getByRole("link", { name: ORDERING });
  const href = await row.getAttribute("href");
  const projectId = (href ?? "").split("/")[3] ?? "";
  await page.goto(`/client/projects/${projectId}/bids`);
  const visible = (text: string | RegExp) => page.getByText(text).filter({ visible: true }).first();
  await expect(visible("Shakib Hasan")).toBeVisible();
  // The two documented ineligible reasons are shown.
  await expect(visible("Can’t meet the deadline")).toBeVisible();
  await expect(visible("No passing skill test")).toBeVisible();
  await expect(page.getByText(/12 bids, 10 eligible/)).toBeVisible();
  await shot(page, info, "02-client-bids");
  // Why is the newcomer eligible? The newcomer rule, check by check.
  await page
    .getByRole("button", { name: "Why eligible: Nadia Rahman" })
    .filter({ visible: true })
    .click();
  await expect(page.getByText("Eligible through the newcomer rule: React test 85%.")).toBeVisible();
  await shot(page, info, "02b-why-newcomer");
  await closeDialog(page, "Nadia Rahman");

  // 3. The too-few-bids banner on the short project.
  await page.goto("/client/projects");
  await page.getByRole("link", { name: "Mobile companion app" }).click();
  await expect(page).toHaveURL(/\/plan$/);
  const shortId = page.url().split("/")[5] ?? "";
  await page.goto(`/client/projects/${shortId}/bids`);
  await expect(page.getByText("Not enough eligible bids yet")).toBeVisible();
  await shot(page, info, "03-too-few");
  await page.getByRole("button", { name: "Fix the shortfall" }).click();
  await expect(page.getByRole("dialog", { name: "Fix the shortfall" })).toBeVisible();
  await shot(page, info, "03b-fix-shortfall");
  await closeDialog(page, "Fix the shortfall");

  // 4. A newcomer searches, opens the project and sees the live eligibility preview.
  await loginSeeded(page, url, "nadia@devsync.local");
  await page.goto("/dev/find");
  await page.getByLabel("Search projects", { exact: true }).fill("ordering");
  await expect(page.getByRole("link", { name: ORDERING }).first()).toBeVisible();
  await shot(page, info, "04-find-work");
  // Every seeded developer already bid on the ordering project; Nadia hasn't on the short one.
  await page.goto(`/dev/projects/${shortId}`);
  await page.getByRole("combobox").click();
  await page.getByRole("option", { name: /React/ }).first().click();
  // Fill and confirm each value (Firefox once dropped a fill that raced the form's first render).
  for (const [label, value] of [
    [/Your price/, "18000"],
    [/Days you need/, "20"],
  ] as const) {
    const field = page.getByLabel(label);
    await expect(async () => {
      await field.fill(value);
      await expect(field).toHaveValue(value, { timeout: 1000 });
    }).toPass({ timeout: 10_000 });
  }
  await expect(page.getByText(/meet every requirement|would be filtered out/i)).toBeVisible({
    timeout: 5000,
  });
  await shot(page, info, "05-bid-sheet-eligibility");
});
