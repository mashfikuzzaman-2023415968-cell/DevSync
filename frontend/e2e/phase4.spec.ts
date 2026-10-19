/**
 * Phase 4 flows (spec §17 Phase 4 tests, Demo 1 walkthrough §17.0): a client builds the §18.2
 * "Online ordering system" plan in the wizard, sees the critical path and Frontend's 4 days of
 * slack, has a circular dependency rejected, verifies a (simulated) payment method, publishes,
 * and cancels a draft by typing its title. Plus layout, axe and CSP checks on screens that need
 * an object id or a later wizard step.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Locator, Page } from "@playwright/test";
import { expect, test } from "./test";
import { apiSignIn, watchPage } from "./fixtures";
import { layoutProblems } from "./layout-checks";

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

async function serious(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

/** No overflow, overlaps or small touch targets at phone, tablet and desktop widths; axe clean. */
async function checkScreen(page: Page, name: string) {
  const found: string[] = [];
  for (const [width, height, touch] of [
    [375, 667, true],
    [768, 1024, true],
    [1440, 900, false],
  ] as const) {
    await page.setViewportSize({ width, height });
    await page.waitForTimeout(150);
    const problems = await page.evaluate(layoutProblems, { touch });
    found.push(...problems.map((p) => `${name} ${String(width)}: ${p}`));
  }
  await page.setViewportSize({ width: 1280, height: 800 });
  found.push(...(await serious(page)).map((v) => `${name} axe: ${v}`));
  return found;
}

function milestoneRow(page: Page, index: number): Locator {
  return page.locator("li", { has: page.getByLabel("Name", { exact: true }) }).nth(index);
}

async function next(page: Page) {
  await page.getByRole("button", { name: "Continue" }).click();
}

test("a client plans the §18.2 project, sees the critical path, and publishes it @e2e", async ({
  page,
  baseURL,
}) => {
  test.setTimeout(180_000);
  const origin = new URL(baseURL ?? "https://localhost").origin;
  const w = await watchPage(page, origin);
  await apiSignIn(page, baseURL ?? "", "CLIENT", "Rahim Uddin");
  await page.goto("/client/projects/new");

  // 1 Info
  await page.getByLabel("Project title").fill("Online ordering system");
  await page.getByLabel("One-line summary").fill("Customers order online; staff track orders.");
  await next(page);

  // 2 Requirements and deadline
  await page.getByLabel("Requirements").fill("Ordering, payments (simulated), order tracking.");
  await page.getByLabel("Deadline (days)").fill("30");
  await next(page);

  // 3 Skills and team: four slots, one person each (team of 4).
  for (let i = 1; i < SLOTS.length; i += 1) {
    await page.getByRole("button", { name: "Add slot" }).click();
  }
  for (const [i, skill] of SLOTS.entries()) {
    await page.getByRole("combobox").nth(i).click();
    await page.getByRole("option", { name: skill, exact: true }).click();
  }
  await expect(page.getByText("Team size:")).toContainText("4");
  await next(page);

  // 4 Milestones: the six milestones with durations, shares and dependencies.
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

  // The Gantt names the critical path and Frontend's slack (§18.2 golden values).
  const gantt = page.getByRole("img", { name: /critical/i }).first();
  await expect(gantt).toBeVisible();
  await expect(page.getByLabel("Frontend: days 4–13, slack 4 days")).toBeVisible();
  await expect(page.getByLabel("Backend API: days 9–17, on the critical path")).toBeVisible();
  const issues = await checkScreen(page, "wizard-milestones");

  // A circular dependency is shown and blocks Continue (Demo 1 walkthrough).
  const first = milestoneRow(page, 0);
  await first.getByRole("button", { name: "Testing & launch", exact: true }).click();
  await expect(page.getByText(/depend on each other in a loop/i)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("button", { name: "Continue" })).toBeDisabled();
  await first.getByRole("button", { name: "Testing & launch", exact: true }).click();
  await expect(page.getByText("Duration 24 days")).toBeVisible({ timeout: 10_000 });

  // The table view lists every milestone with its slack.
  await page.getByRole("radio", { name: "Table" }).click();
  const frontendRow = page.getByRole("row", { name: /Frontend/ });
  await expect(frontendRow).toContainText("4");
  await next(page);

  // 5 Budget
  await page.getByLabel("Budget (৳)").fill("120000");
  await next(page);

  // 6 Review: verify the (simulated) payment method, then publish.
  await expect(page.getByText("Review and publish")).toBeVisible();
  const publish = page.getByRole("button", { name: "Publish for bidding" });
  await expect(publish).toBeDisabled();
  await page.getByRole("button", { name: "Verify payment method" }).click();
  await expect(page.getByText("Payment method verified").first()).toBeVisible();
  await expect(publish).toBeEnabled();
  await publish.click();

  // The plan page shows the published plan.
  await expect(page).toHaveURL(/\/client\/projects\/[0-9a-f-]+\/plan$/, { timeout: 15_000 });
  await expect(
    page.getByRole("heading", { level: 1, name: "Plan: Online ordering system" }),
  ).toBeVisible();
  await expect(page.getByLabel("Frontend: days 4–13, slack 4 days")).toBeVisible();
  issues.push(...(await checkScreen(page, "plan-page")));

  // My projects lists it as open for bids.
  await page.goto("/client/projects");
  await expect(page.getByRole("link", { name: "Online ordering system" })).toBeVisible();
  await expect(page.getByText("Bidding").first()).toBeVisible();

  expect(issues).toEqual([]);
  expect(await w.violations()).toEqual([]);
  expect(w.consoleErrors).toEqual([]);
  expect(w.foreign).toEqual([]);
});

test("a client cancels a draft by giving a reason and typing its title @e2e", async ({
  page,
  baseURL,
}) => {
  await apiSignIn(page, baseURL ?? "", "CLIENT", "Rahim Uddin");
  await page.goto("/client/projects/new");
  await page.getByLabel("Project title").fill("Warehouse scanner app");
  await next(page); // saves the draft
  await expect(page.getByText("Requirements and deadline")).toBeVisible();

  await page.goto("/client/projects");
  const row = page.locator("li", {
    has: page.getByRole("link", { name: "Warehouse scanner app" }),
  });
  await expect(row.getByText("Draft")).toBeVisible();
  await row.getByRole("button", { name: "Cancel" }).click();
  const dialog = page.getByRole("dialog", { name: "Cancel this project?" });
  await dialog.getByLabel("Reason").fill("Re-scoping with the warehouse team.");
  const confirm = dialog.getByRole("button", { name: "Cancel project" });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel(/Type “Warehouse scanner app” to confirm/).fill("Warehouse scanner app");
  await confirm.click();
  await expect(row.getByText("Cancelled")).toBeVisible();
  await expect(row.getByRole("button", { name: "Cancel" })).toHaveCount(0);
});

test("leaving the wizard with unsaved changes asks first @e2e", async ({ page, baseURL }) => {
  await apiSignIn(page, baseURL ?? "", "CLIENT", "Rahim Uddin");
  await page.goto("/client/projects/new");
  await page.getByLabel("Project title").fill("Unsaved idea");
  await page.getByRole("link", { name: "Dashboard" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Leave without saving?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Stay on this step" }).click();
  await expect(page.getByLabel("Project title")).toHaveValue("Unsaved idea");
  await page.getByRole("link", { name: "Dashboard" }).first().click();
  await page
    .getByRole("dialog", { name: "Leave without saving?" })
    .getByRole("button", { name: "Leave without saving" })
    .click();
  await expect(page).toHaveURL(/\/client$/);
});
