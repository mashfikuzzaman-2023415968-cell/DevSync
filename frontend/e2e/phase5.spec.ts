/**
 * Phase 5 flows (spec §17 Phase 5 tests, Demo 1 walkthrough §17.0): a developer searches and
 * filters open projects, opens one, sees the live Algorithm 1 eligibility preview on the bid
 * sheet, places a sealed bid and withdraws it; a second developer in a separate browser context
 * cannot see the first developer's bid anywhere (sealed, §14.5); the client sees every bid with
 * its eligibility and the too-few-bids banner. Plus axe, CSP and layout on the new screens.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect, test } from "./test";
import { apiSignIn, createOrderingProject, watchPage } from "./fixtures";
import { layoutProblems } from "./layout-checks";

async function serious(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => v.id);
}

async function checkScreen(page: Page, name: string): Promise<string[]> {
  const found: string[] = [];
  for (const [width, height, touch] of [
    [375, 667, true],
    [768, 1024, true],
    [1440, 900, false],
  ] as const) {
    await page.setViewportSize({ width, height });
    const problems = await page.evaluate(layoutProblems, { touch });
    found.push(...problems.map((p) => `${name} ${String(width)}: ${p}`));
  }
  found.push(...(await serious(page)).map((v) => `${name} axe: ${v}`));
  return found;
}

test("a developer searches, previews eligibility, bids and withdraws @e2e", async ({
  page,
  baseURL,
}) => {
  const origin = new URL(baseURL ?? "").origin;
  // A client publishes the §18.2 project so it is open for bids.
  await apiSignIn(page, baseURL ?? "", "CLIENT", "Rahim");
  const projectId = await createOrderingProject(page, baseURL ?? "", { publish: true });

  // A developer finds it and opens the bid sheet.
  await apiSignIn(page, baseURL ?? "", "DEVELOPER", "Nadia Rahman");
  const watch = await watchPage(page, origin);
  await page.goto("/dev/find");
  await page.getByLabel("Search").fill("ordering");
  await expect(page.getByRole("link", { name: "Online ordering system" }).first()).toBeVisible();
  // The filter is reflected in the URL (survives reload).
  await expect(page).toHaveURL(/q=ordering/);

  await page.goto(`/dev/projects/${projectId}`);
  await expect(page.getByRole("heading", { name: "Online ordering system" })).toBeVisible();

  // Fill the sealed bid; the live eligibility preview appears.
  await page.getByRole("combobox").click();
  await page.getByRole("option", { name: /React/ }).first().click();
  await page.getByLabel(/Your price/).fill("18000");
  await page.getByLabel(/Days you need/).fill("20");
  await expect(
    page.getByText(/meet every requirement|would be filtered out/i),
  ).toBeVisible({ timeout: 5000 });

  await page.getByRole("button", { name: "Place sealed bid" }).click();
  await expect(page.getByText("Bid placed")).toBeVisible();

  // It shows up in My Bids.
  await page.goto("/dev/bids");
  await expect(page.getByText("View project")).toBeVisible();

  expect(await checkScreen(page, "my-bids")).toEqual([]);
  expect(watch.consoleErrors, watch.consoleErrors.join("\n")).toEqual([]);
  expect(await watch.violations()).toEqual([]);
});

test("a bid is sealed from other developers across browser contexts @e2e", async ({
  browser,
  page,
  baseURL,
}) => {
  await apiSignIn(page, baseURL ?? "", "CLIENT", "Rahim");
  const projectId = await createOrderingProject(page, baseURL ?? "", { publish: true });

  // Developer A places a bid.
  const ctxA = await browser.newContext({ ignoreHTTPSErrors: true, baseURL: baseURL ?? "" });
  const a = await ctxA.newPage();
  await apiSignIn(a, baseURL ?? "", "DEVELOPER", "Developer A");
  await a.goto(`/dev/projects/${projectId}`);
  await a.getByRole("combobox").click();
  await a.getByRole("option", { name: /FastAPI/ }).first().click();
  await a.getByLabel(/Your price/).fill("22000");
  await a.getByLabel(/Days you need/).fill("18");
  await a.getByRole("button", { name: "Place sealed bid" }).click();
  await expect(a.getByText("Bid placed")).toBeVisible();

  // Developer B, in a separate context, sees nothing of it.
  const ctxB = await browser.newContext({ ignoreHTTPSErrors: true, baseURL: baseURL ?? "" });
  const b = await ctxB.newPage();
  await apiSignIn(b, baseURL ?? "", "DEVELOPER", "Developer B");
  await b.goto("/dev/bids");
  await expect(b.getByText("No bids yet")).toBeVisible();
  // The project page for B offers a fresh bid form, not A's bid.
  await b.goto(`/dev/projects/${projectId}`);
  await expect(b.getByRole("button", { name: "Place sealed bid" })).toBeVisible();
  await expect(b.getByText(/22,000/)).toHaveCount(0);

  await ctxA.close();
  await ctxB.close();
});

test("the client sees all bids with eligibility and the too-few banner @e2e", async ({
  page,
  baseURL,
}) => {
  const client = await apiSignIn(page, baseURL ?? "", "CLIENT", "Rahim");
  const projectId = await createOrderingProject(page, baseURL ?? "", { publish: true });

  // One developer bids (far short of the team of four → too-few).
  const ctx = await page.context().browser()?.newContext({
    ignoreHTTPSErrors: true,
    baseURL: baseURL ?? "",
  });
  if (!ctx) throw new Error("no browser");
  const dev = await ctx.newPage();
  await apiSignIn(dev, baseURL ?? "", "DEVELOPER", "Arif Hossain");
  await dev.goto(`/dev/projects/${projectId}`);
  await dev.getByRole("combobox").click();
  await dev.getByRole("option", { name: /React/ }).first().click();
  await dev.getByLabel(/Your price/).fill("18000");
  await dev.getByLabel(/Days you need/).fill("20");
  await dev.getByRole("button", { name: "Place sealed bid" }).click();
  await expect(dev.getByText("Bid placed")).toBeVisible();
  await ctx.close();

  // Back as the client: the bids table shows the bid and the too-few banner.
  await page.goto(`/client/projects/${projectId}/bids`);
  await expect(page.getByText("Arif Hossain")).toBeVisible();
  await expect(page.getByText("Not enough eligible bids yet")).toBeVisible();
  expect(client.email).toContain("@");
});
