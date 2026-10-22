/**
 * Phase 5 flows (spec §17 Phase 5 tests, Demo 1 walkthrough §17.0): a developer searches and
 * filters open projects, opens one, sees the live Algorithm 1 eligibility preview on the bid
 * sheet, places a sealed bid and withdraws it; a second developer in a separate browser context
 * cannot see the first developer's bid anywhere (sealed, §14.5); the client sees every bid with
 * its eligibility and the too-few-bids banner. Follow-ups (D54): withdraw then bid again; the
 * client sees why each bid is (not) eligible — the newcomer rule and automatic relaxation
 * included — filters the bids and fixes a shortfall by previewing then raising the budget and
 * extending bidding; after the bidding deadline the bid sheet is closed. Plus axe, CSP and
 * layout on the new screens.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect, test } from "./test";
import {
  addSkillEvidence,
  apiSignIn,
  closeBidding,
  createOrderingProject,
  setReputation,
  watchPage,
} from "./fixtures";
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
  await page.getByLabel("Search projects", { exact: true }).fill("ordering");
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
  await expect(page.getByText(/meet every requirement|would be filtered out/i)).toBeVisible({
    timeout: 5000,
  });

  await page.getByRole("button", { name: "Place sealed bid" }).click();
  await expect(page.getByText("Bid placed").first()).toBeVisible();

  // Withdraw it, then bid again: the sheet opens fresh and the new bid is placed.
  await page.getByRole("button", { name: "Withdraw bid" }).click();
  await expect(page.getByText("Bid withdrawn").first()).toBeVisible();
  await page.getByRole("combobox").click();
  await page.getByRole("option", { name: /React/ }).first().click();
  await page.getByLabel(/Your price/).fill("17500");
  await page.getByLabel(/Days you need/).fill("21");
  await page.getByRole("button", { name: "Place sealed bid" }).click();
  await expect(page.getByText("Bid placed").first()).toBeVisible();
  await expect(page.getByText(/You bid ৳17,500/)).toBeVisible();

  // It shows up in My Bids.
  await page.goto("/dev/bids");
  await expect(page.getByText("View project").first()).toBeVisible();

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
  await a
    .getByRole("option", { name: /FastAPI/ })
    .first()
    .click();
  await a.getByLabel(/Your price/).fill("22000");
  await a.getByLabel(/Days you need/).fill("18");
  await a.getByRole("button", { name: "Place sealed bid" }).click();
  await expect(a.getByText("Bid placed").first()).toBeVisible();

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
  const ctx = await page
    .context()
    .browser()
    ?.newContext({
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
  await expect(dev.getByText("Bid placed").first()).toBeVisible();
  await ctx.close();

  // Back as the client: the bids table shows the bid and the too-few banner.
  await page.goto(`/client/projects/${projectId}/bids`);
  await expect(page.getByText("Arif Hossain").filter({ visible: true }).first()).toBeVisible();
  await expect(page.getByText("Not enough eligible bids yet")).toBeVisible();
  expect(client.email).toContain("@");
});

/** As a developer in its own context: bid on a slot of the project. */
async function bidAs(
  page: Page,
  baseURL: string,
  projectId: string,
  name: string,
  setup: (userId: string) => Promise<void>,
  [skill, price, days]: [string, string, string],
): Promise<void> {
  const browser = page.context().browser();
  if (!browser) throw new Error("no browser");
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, baseURL });
  const dev = await ctx.newPage();
  const user = await apiSignIn(dev, baseURL, "DEVELOPER", name);
  await setup(user.userId);
  await dev.goto(`/dev/projects/${projectId}`);
  await dev.getByRole("combobox").click();
  await dev.getByRole("option", { name: skill }).first().click();
  await dev.getByLabel(/Your price/).fill(price);
  await dev.getByLabel(/Days you need/).fill(days);
  await dev.getByRole("button", { name: "Place sealed bid" }).click();
  await expect(dev.getByText("Bid placed").first()).toBeVisible();
  await ctx.close();
}

test("the client sees why each bid is eligible: newcomer rule and relaxation @e2e", async ({
  page,
  baseURL,
}) => {
  const base = baseURL ?? "";
  const origin = new URL(base).origin;
  await apiSignIn(page, base, "CLIENT", "Rahim");
  const projectId = await createOrderingProject(page, base, { publish: true });
  const req = page.request;

  // Nadia: a newcomer with an 85% React test → eligible through the newcomer rule.
  await bidAs(
    page,
    base,
    projectId,
    "Nadia Rahman",
    (id) => addSkillEvidence(req, base, id, "React", 0.85),
    ["React", "18000", "20"],
  );
  // Shakib: experienced, P 42 (below 45) → eligible only after automatic relaxation.
  await bidAs(
    page,
    base,
    projectId,
    "Shakib Hasan",
    async (id) => {
      await addSkillEvidence(req, base, id, "FastAPI", 0.7);
      await setReputation(req, base, id, 0.42, 0.6);
    },
    ["FastAPI", "22000", "18"],
  );
  // Lamia: a newcomer without a passing FastAPI test → filtered out.
  await bidAs(
    page,
    base,
    projectId,
    "Lamia Akter",
    (id) => addSkillEvidence(req, base, id, "FastAPI", 0.4),
    ["FastAPI", "21000", "25"],
  );

  const watch = await watchPage(page, origin);
  await page.goto(`/client/projects/${projectId}/bids`);
  await expect(page.getByText("Minimums relaxed to find candidates")).toBeVisible();
  await expect(page.getByText(/3 bids, 2 eligible/)).toBeVisible();

  // Why is Nadia eligible? The newcomer rule, step by step.
  await page
    .getByRole("button", { name: "Why eligible: Nadia Rahman" })
    .filter({ visible: true })
    .click();
  const sheet = page.getByRole("dialog", { name: "Nadia Rahman" });
  await expect(
    sheet.getByText("Eligible through the newcomer rule: React test 85%."),
  ).toBeVisible();
  await expect(sheet.getByText("How the filter decided")).toBeVisible();
  await expect(sheet.getByText("React test 85% (newcomers need 60%)")).toBeVisible();
  const issues = await checkScreen(page, "client-bids-why");
  await page.keyboard.press("Escape");

  // Why not Lamia? The first failing check is named.
  await page
    .getByRole("button", { name: "Why not eligible: Lamia Akter" })
    .filter({ visible: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Lamia Akter" }).getByText(/Filtered out: FastAPI test 40%/),
  ).toBeVisible();
  await page.keyboard.press("Escape");

  // Filters: only the ineligible bid, then a slot with no bids matching.
  await page.getByRole("radio", { name: "Not eligible" }).click();
  await expect(page.getByText("Lamia Akter").filter({ visible: true }).first()).toBeVisible();
  await expect(page.getByText("Nadia Rahman").filter({ visible: true })).toHaveCount(0);
  await page.getByRole("radio", { name: "All" }).click();

  issues.push(...(await checkScreen(page, "client-bids")));
  expect(issues).toEqual([]);
  expect(watch.consoleErrors, watch.consoleErrors.join("\n")).toEqual([]);
  expect(await watch.violations()).toEqual([]);
});

test("the client previews a fix for the shortfall, raises the budget and extends @e2e", async ({
  page,
  baseURL,
}) => {
  const base = baseURL ?? "";
  await apiSignIn(page, base, "CLIENT", "Rahim");
  const projectId = await createOrderingProject(page, base, { publish: true });
  // An experienced React developer over budget: eligible once the budget is raised.
  await bidAs(
    page,
    base,
    projectId,
    "Arif Hossain",
    async (id) => {
      await addSkillEvidence(page.request, base, id, "React", 0.9);
      await setReputation(page.request, base, id, 0.8, 0.75);
    },
    ["React", "119000", "20"],
  );

  await page.goto(`/client/projects/${projectId}/bids`);
  await expect(page.getByText("Not enough eligible bids yet")).toBeVisible();
  await page.getByRole("button", { name: "Fix the shortfall" }).click();
  const dialog = page.getByRole("dialog", { name: "Fix the shortfall" });
  await expect(dialog).toBeVisible();
  const issues = await checkScreen(page, "fix-shortfall");

  // Raise the budget: the effect shows before confirming.
  await dialog.getByRole("tab", { name: "Raise budget" }).click();
  await dialog.getByLabel("New budget (৳)").fill("140000");
  await expect(dialog.getByTestId("terms-effect")).toContainText("1 more bid would be eligible");
  await dialog.getByRole("button", { name: "Raise the budget" }).click();
  await expect(page.getByText("Budget raised").first()).toBeVisible();
  await expect(page.getByText(/1 eligible/)).toBeVisible();

  // Still short of a team of four: extend bidding.
  await page.getByRole("button", { name: "Fix the shortfall" }).click();
  await page.getByRole("tab", { name: "Extend" }).click();
  await page.getByRole("button", { name: /Extend bidding by 3 days/ }).click();
  await expect(page.getByText("Bidding extended by 3 days").first()).toBeVisible();

  // The floors hold: lowering standards offers only 30–45 and 25–40.
  await page.getByRole("button", { name: "Fix the shortfall" }).click();
  await page.getByRole("tab", { name: "Lower standards" }).click();
  await expect(page.getByText(/down to 30 for performance and 25 for competency/)).toBeVisible();
  await page.keyboard.press("Escape");
  expect(issues).toEqual([]);
});

test("after the bidding deadline the bid sheet is closed @e2e", async ({ page, baseURL }) => {
  const base = baseURL ?? "";
  await apiSignIn(page, base, "CLIENT", "Rahim");
  const projectId = await createOrderingProject(page, base, { publish: true });
  await apiSignIn(page, base, "DEVELOPER", "Tanvir Ahmed");
  await page.goto(`/dev/projects/${projectId}`);
  await page.getByRole("combobox").click();
  await page
    .getByRole("option", { name: /Testing/ })
    .first()
    .click();
  await page.getByLabel(/Your price/).fill("15000");
  await page.getByLabel(/Days you need/).fill("12");
  await page.getByRole("button", { name: "Place sealed bid" }).click();
  await expect(page.getByText("Bid placed").first()).toBeVisible();

  await closeBidding(page.request, base, projectId);
  await page.reload();
  await expect(
    page.getByText("Bidding has closed, so this bid can no longer be changed."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Withdraw bid" })).toHaveCount(0);
  // It is gone from Find Projects.
  await page.goto("/dev/find");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator(`a[href="/dev/projects/${projectId}"]`)).toHaveCount(0);
});
