/**
 * Demo 1 walkthrough (spec §17.0), run by `make demo-check DEMO=1` on chromium, firefox, webkit
 * and a mobile viewport (three times) to produce rehearsal screenshots and a report. It drives
 * the **seeded** Stage-1 data (`make seed-demo STAGE=1`), so it shows the real documented bids:
 * the client sees all 12 with eligibility and the two ineligible reasons, the too-few-bids banner
 * appears on the short project, and a newcomer sees the live eligibility preview on the bid sheet.
 *
 * Login uses the seeded demo accounts (printed by the seed). Registration, email/OTP verification
 * and admin TOTP are shown live in the demo and covered by the Phase 1 E2E; this spec focuses on
 * the Phase 4–5 highlights (the CPM plan and sealed bidding with Algorithm 1 filtering).
 */
import type { Page, TestInfo } from "@playwright/test";
import { expect, test } from "../test";
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
  await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true });
}

test("Demo 1 — planning, sealed bidding and Algorithm 1 filtering @demo", async ({
  page,
  baseURL,
}, info) => {
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
  await expect(page.getByText("Shakib Hasan")).toBeVisible();
  // The two documented ineligible reasons are shown.
  await expect(page.getByText(/Too slow/i)).toBeVisible();
  await expect(page.getByText(/No passing skill test/i)).toBeVisible();
  await shot(page, info, "02-client-bids");

  // 3. The too-few-bids banner on the short project.
  await page.goto("/client/projects");
  await page.getByRole("link", { name: "Mobile companion app" }).click();
  await expect(page).toHaveURL(/\/plan$/);
  const shortId = page.url().split("/")[5] ?? "";
  await page.goto(`/client/projects/${shortId}/bids`);
  await expect(page.getByText("Not enough eligible bids yet")).toBeVisible();
  await shot(page, info, "03-too-few");

  // 4. A newcomer searches, opens the project and sees the live eligibility preview.
  await loginSeeded(page, url, "nadia@devsync.local");
  await page.goto("/dev/find");
  await page.getByLabel("Search projects", { exact: true }).fill("ordering");
  await expect(page.getByRole("link", { name: ORDERING }).first()).toBeVisible();
  await shot(page, info, "04-find-work");
  await page.goto(`/dev/projects/${projectId}`);
  await page.getByRole("combobox").click();
  await page.getByRole("option", { name: /React/ }).first().click();
  await page.getByLabel(/Your price/).fill("18000");
  await page.getByLabel(/Days you need/).fill("20");
  await expect(page.getByText(/meet every requirement|would be filtered out/i)).toBeVisible({
    timeout: 5000,
  });
  await shot(page, info, "05-bid-sheet-eligibility");
});
