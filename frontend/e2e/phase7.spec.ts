/**
 * Phase 7 end to end (spec §17 Phase 7, Demo 2 walkthrough §17.0): on a FORMING ordering
 * project with a qualified newcomer, the client forms a team with the fairness dial at 1 and
 * sees it live (swarm, then the result): the newcomer is in the team, the exact solver says
 * "Optimal", the cost of fairness and "why this team" are shown, and the best teams can be
 * compared. Recalculating with the Budget preset changes the Testing developer. The client
 * confirms; a developer who wasn't selected reads a correct "why not selected" that names
 * nobody else. Plus axe and layout on the new screen.
 *
 * The test stack runs no worker: the run is executed through the test-only router while the
 * page follows it over the job's event stream, through Nginx.
 */
import AxeBuilder from "@axe-core/playwright";
import type { APIRequestContext, BrowserContext, Page } from "@playwright/test";
import {
  addSkillEvidence,
  apiSignIn,
  createOrderingProject,
  csrfHeaders,
  qualifyFor,
  setReputation,
  slotFor,
  watchPage,
} from "./fixtures";
import { layoutProblems } from "./layout-checks";
import { expect, test } from "./test";

interface Bidder {
  ctx: BrowserContext;
  page: Page;
  bidId: string;
}

/** A developer in their own browser context bids on a slot through the API. */
async function bidAs(
  page: Page,
  baseURL: string,
  projectId: string,
  name: string,
  skill: string,
  [price, days]: [number, number],
  setup: (req: APIRequestContext, userId: string) => Promise<void>,
): Promise<Bidder> {
  const browser = page.context().browser();
  if (!browser) throw new Error("no browser");
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, baseURL });
  const dev = await ctx.newPage();
  const user = await apiSignIn(dev, baseURL, "DEVELOPER", name);
  await setup(dev.request, user.userId);
  const r = await dev.request.post(`/api/v1/projects/${projectId}/bids`, {
    headers: await csrfHeaders(dev.request, baseURL),
    data: {
      slot_id: await slotFor(dev.request, projectId, skill),
      price_paisa: price * 100,
      days_needed: days,
    },
  });
  if (r.status() !== 201) throw new Error(`bid → ${String(r.status())} ${await r.text()}`);
  return { ctx, page: dev, bidId: ((await r.json()) as { id: string }).id };
}

async function post(page: Page, baseURL: string, path: string): Promise<unknown> {
  const r = await page.request.post(path, { headers: await csrfHeaders(page.request, baseURL) });
  if (!r.ok()) throw new Error(`${path} → ${String(r.status())} ${await r.text()}`);
  return r.status() === 204 ? null : ((await r.json()) as unknown);
}

/** Start a run from the page and execute it, returning the run id. */
async function formTeam(page: Page, baseURL: string, label: RegExp): Promise<string> {
  const started = page.waitForResponse(
    (r) => r.url().endsWith("/formation-runs") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: label }).click();
  const accepted = (await (await started).json()) as { run_id: string };
  await expect(page.getByText("Searching for the best team…")).toBeVisible();
  const done = (await post(
    page,
    baseURL,
    `/api/v1/__test__/formation-runs/${accepted.run_id}/execute`,
  )) as { status: string };
  expect(done.status).toBe("SUCCEEDED");
  return accepted.run_id;
}

async function serious(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => v.id);
}

test("the client forms a fair, verified team and a non-selected developer learns why @e2e", async ({
  page,
  baseURL,
}) => {
  test.setTimeout(240_000);
  const base = baseURL ?? "";
  const origin = new URL(base).origin;
  await apiSignIn(page, base, "CLIENT", "Rahim Uddin");
  const projectId = await createOrderingProject(page, base, { publish: true });
  const experienced = (skill: string, p: number, c: number) => async (
    req: APIRequestContext,
    id: string,
  ) => {
    await addSkillEvidence(req, base, id, skill, 0.8);
    await setReputation(req, base, id, p, c);
  }; // prettier-ignore

  const nadia = await bidAs(page, base, projectId, "Nadia Rahman", "React", [18_000, 20],
    (req, id) => qualifyFor(req, base, id, projectId, "React")); // prettier-ignore
  const arif = await bidAs(page, base, projectId, "Arif Hossain", "React", [26_000, 18],
    experienced("React", 0.85, 0.82)); // prettier-ignore
  const tanvir = await bidAs(page, base, projectId, "Tanvir Ahmed", "FastAPI", [25_000, 20],
    experienced("FastAPI", 0.75, 0.7)); // prettier-ignore
  const sadia = await bidAs(page, base, projectId, "Sadia Islam", "PostgreSQL", [23_000, 21],
    experienced("PostgreSQL", 0.78, 0.74)); // prettier-ignore
  // Testing: Imran is better and quicker but dear, Zahid cheap; Balanced picks Imran and the
  // Budget preset Zahid (see the arithmetic in docs/ALGORITHMS.md's presets note).
  const imran = await bidAs(page, base, projectId, "Imran Kabir", "Testing", [40_000, 15],
    experienced("Testing", 0.85, 0.85)); // prettier-ignore
  const zahid = await bidAs(page, base, projectId, "Zahid Mahmud", "Testing", [15_000, 22],
    experienced("Testing", 0.6, 0.55)); // prettier-ignore
  await post(page, base, `/api/v1/__test__/projects/${projectId}/start-forming`);

  const watch = await watchPage(page, origin);
  await page.goto(`/client/projects/${projectId}/bids`);
  await page.getByRole("link", { name: "Form team" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Form your team" })).toBeVisible();
  await expect(page.getByText("No team yet")).toBeVisible();
  // The dial defaults to 1: a qualified newcomer made the shortlist.
  await expect(page.getByRole("radio", { name: "1" })).toBeChecked();

  await formTeam(page, base, /^Form team$/);
  await expect(page.getByText("Optimal (exact check)")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("1 newcomer included")).toBeVisible();
  const cards = page.locator("[data-card]");
  await expect(cards.filter({ hasText: "Nadia Rahman" }).getByText("Newcomer")).toBeVisible();
  await expect(cards.filter({ hasText: "Imran Kabir" }).first()).toBeVisible();
  await expect(page.getByText("Why this team?")).toBeVisible();
  await expect(page.getByText(/^Cost of fairness$/)).toBeVisible();
  await page.getByRole("button", { name: "Compare" }).click();
  await expect(page.getByText("Recommended").first()).toBeVisible();
  // The convergence chart has a table view.
  const chart = cards.filter({ hasText: "How the search converged" });
  await chart.getByRole("radio", { name: "View as table" }).click();
  await expect(chart.getByRole("table")).toBeVisible();

  const found: string[] = [];
  for (const [width, height, touch] of [
    [375, 667, true],
    [768, 1024, true],
    [1440, 900, false],
  ] as const) {
    await page.setViewportSize({ width, height });
    found.push(...(await page.evaluate(layoutProblems, { touch })).map((p) => `${String(width)}: ${p}`));
  } // prettier-ignore
  found.push(...(await serious(page)).map((v) => `axe: ${v}`));
  expect(found).toEqual([]);
  await page.setViewportSize({ width: 1440, height: 900 });

  // Recalculate with the Budget preset: the cheaper Testing developer comes in.
  await page.getByRole("radio", { name: "Budget" }).click();
  await formTeam(page, base, /^Recalculate$/);
  await expect(cards.filter({ hasText: "Zahid Mahmud" }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: /^Budget, 1 newcomer/ })).toBeVisible();

  // Confirm the team.
  await page.getByRole("button", { name: "Confirm team" }).click();
  const dialog = page.getByRole("alertdialog", { name: "Confirm this team?" });
  await dialog.getByRole("button", { name: "Confirm team" }).click();
  await expect(page.getByText("Team confirmed").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Recalculate" })).toHaveCount(0);
  expect(watch.consoleErrors).toEqual([]);
  expect(watch.foreign).toEqual([]);
  expect(await watch.violations()).toEqual([]);

  // Arif (not selected: the dial kept the React place for Nadia) reads why.
  const runs = (await (
    await page.request.get(`/api/v1/projects/${projectId}/formation-runs`)
  ).json()) as { id: string; confirmed: boolean }[];
  const confirmed = runs.find((r) => r.confirmed)?.id ?? "";
  await post(page, base, `/api/v1/__test__/formation-runs/${confirmed}/explanations`);
  await arif.page.goto(`/dev/bids/${arif.bidId}`);
  const why = arif.page.locator("[data-card]").filter({ hasText: "Why it wasn’t selected" });
  await expect(why).toBeVisible();
  await expect(why.getByText(/another combination of developers scored higher/)).toBeVisible();
  await expect(why).not.toContainText("Nadia");
  // Nadia was selected: her bid shows it, with no explanation card.
  await nadia.page.goto(`/dev/bids/${nadia.bidId}`);
  await expect(nadia.page.getByText("Selected").first()).toBeVisible();
  await expect(nadia.page.getByText("Why it wasn’t selected")).toHaveCount(0);
  // Sealed: Arif can't read anyone else's explanation.
  const other = await arif.page.request.get(`/api/v1/bids/${zahid.bidId}/explanation`);
  expect(other.status()).toBe(404);

  for (const b of [nadia, arif, tanvir, sadia, imran, zahid]) await b.ctx.close();
});
