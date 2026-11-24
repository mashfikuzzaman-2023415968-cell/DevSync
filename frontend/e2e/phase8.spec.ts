/**
 * Phase 8 end to end (spec §17 Phase 8, Demo 2 walkthrough §17.0; FR-INV-1..5): a confirmed team
 * sends invitations; developers answer them on their dashboards (one accepts in the browser, one
 * declines with a reason); the client's Team screen shows the decline and the repair job's ranked
 * replacement with its impact; the client invites it, the replacement accepts, the client
 * confirms the recommended lead and starts the project; the workspace's Team tab opens for the
 * team, and the developers' notifications and bell count show what happened. Plus axe and
 * layout on the new screens.
 *
 * The test stack runs no worker: formation and repair run through the test-only router (D133).
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

interface Dev {
  ctx: BrowserContext;
  page: Page;
  name: string;
}

async function newDev(page: Page, baseURL: string, name: string) {
  const browser = page.context().browser();
  if (!browser) throw new Error("no browser");
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, baseURL });
  const dev = await ctx.newPage();
  const user = await apiSignIn(dev, baseURL, "DEVELOPER", name);
  return { ctx, page: dev, userId: user.userId };
}

async function bidAs(
  page: Page,
  baseURL: string,
  projectId: string,
  name: string,
  skill: string,
  [price, days]: [number, number],
  setup: (req: APIRequestContext, userId: string) => Promise<void>,
): Promise<Dev> {
  const { ctx, page: dev, userId } = await newDev(page, baseURL, name);
  await setup(dev.request, userId);
  const r = await dev.request.post(`/api/v1/projects/${projectId}/bids`, {
    headers: await csrfHeaders(dev.request, baseURL),
    data: {
      slot_id: await slotFor(dev.request, projectId, skill),
      price_paisa: price * 100,
      days_needed: days,
    },
  });
  if (r.status() !== 201) throw new Error(`bid → ${String(r.status())} ${await r.text()}`);
  return { ctx, page: dev, name };
}

async function post(page: Page, baseURL: string, path: string, data?: unknown): Promise<unknown> {
  const r = await page.request.post(path, {
    headers: await csrfHeaders(page.request, baseURL),
    ...(data === undefined ? {} : { data }),
  });
  if (!r.ok()) throw new Error(`${path} → ${String(r.status())} ${await r.text()}`);
  return r.status() === 204 ? null : ((await r.json()) as unknown);
}

/** Accept the developer's pending invitation for the project through the API. */
async function acceptByApi(dev: Dev, baseURL: string, projectId: string): Promise<void> {
  const mine = (await (await dev.page.request.get("/api/v1/me/invitations")).json()) as {
    invitations: { id: string; project_id: string; state: string }[];
  };
  const inv = mine.invitations.find((i) => i.project_id === projectId && i.state === "PENDING");
  if (!inv) throw new Error(`${dev.name} has no pending invitation`);
  await post(dev.page, baseURL, `/api/v1/invitations/${inv.id}/accept`);
}

/** Layout at three sizes plus serious/critical axe findings on the current page. */
async function problems(page: Page): Promise<string[]> {
  const found: string[] = [];
  for (const [width, height, touch] of [
    [375, 667, true],
    [768, 1024, true],
    [1440, 900, false],
  ] as const) {
    await page.setViewportSize({ width, height });
    found.push(...(await page.evaluate(layoutProblems, { touch })).map((p) => `${String(width)}: ${p}`));
  } // prettier-ignore
  // A card still fading in has partial opacity, which axe measures as low contrast.
  // Looping ones (a skeleton's shimmer) are ignored; they never finish.
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .every(
        (a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity,
      ),
  );
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  found.push(
    ...axe.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => `axe: ${v.id} ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  return found;
}

test("FR-INV-1..5: a declined invitation is repaired, a lead chosen and the project started @e2e", async ({
  page,
  baseURL,
}) => {
  test.setTimeout(300_000);
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
  const tanvir = await bidAs(page, base, projectId, "Tanvir Ahmed", "FastAPI", [25_000, 20],
    experienced("FastAPI", 0.75, 0.7)); // prettier-ignore
  const sadia = await bidAs(page, base, projectId, "Sadia Islam", "PostgreSQL", [23_000, 21],
    experienced("PostgreSQL", 0.78, 0.74)); // prettier-ignore
  // Balanced picks Imran for Testing (as in Phase 7); Zahid is left to replace him.
  const imran = await bidAs(page, base, projectId, "Imran Kabir", "Testing", [40_000, 15],
    experienced("Testing", 0.85, 0.85)); // prettier-ignore
  const zahid = await bidAs(page, base, projectId, "Zahid Mahmud", "Testing", [15_000, 22],
    experienced("Testing", 0.6, 0.55)); // prettier-ignore
  await post(page, base, `/api/v1/__test__/projects/${projectId}/start-forming`);
  const run = (await post(page, base, `/api/v1/projects/${projectId}/formation-runs`, {})) as {
    run_id: string;
  };
  await post(page, base, `/api/v1/__test__/formation-runs/${run.run_id}/execute`);
  await post(page, base, `/api/v1/formation-runs/${run.run_id}/confirm`);

  // FR-INV-1: Nadia sees her invitation with its countdown and accepts it in the browser.
  const devWatch = await watchPage(nadia.page, origin);
  await nadia.page.goto("/dev");
  const banner = nadia.page.getByRole("region", { name: "Your invitations and teams" });
  // After a navigation the dashboard loads several queries; a loaded laptop needs more than 5 s.
  const LOAD = { timeout: 20_000 };
  await expect(banner.getByText("You were selected", { exact: true })).toBeVisible(LOAD);
  await expect(banner.getByText(/(day|h) .*left/)).toBeVisible();
  expect(await problems(nadia.page)).toEqual([]);
  await banner.getByRole("button", { name: "Accept" }).click();
  await expect(banner.getByText(/^You joined\./)).toBeVisible(LOAD);
  expect(devWatch.consoleErrors).toEqual([]);
  expect(await devWatch.violations()).toEqual([]);

  // FR-INV-2: Imran declines with a reason; Tanvir and Sadia accept.
  await imran.page.goto("/dev");
  await imran.page.getByRole("button", { name: "Decline", exact: true }).click(LOAD);
  const decline = imran.page.getByRole("dialog", { name: "Decline this invitation?" });
  await decline.getByRole("textbox").fill("Booked on another project those weeks.");
  await decline.getByRole("button", { name: "Decline invitation" }).click();
  await expect(imran.page.getByText(/You declined the invitation/)).toBeVisible(LOAD);
  await acceptByApi(tanvir, base, projectId);
  await acceptByApi(sadia, base, projectId);

  // FR-INV-3: the client's Teams list flags the open place; the Team screen shows the decline
  // and, once the job runs, Zahid ranked first with the impact. The client invites him.
  const watch = await watchPage(page, origin);
  await page.goto("/client/teams");
  await expect(page.getByText("A place needs a replacement")).toBeVisible(LOAD);
  await page.getByRole("link", { name: "Manage team" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your team" })).toBeVisible();
  await expect(page.getByText("Declined").first()).toBeVisible(LOAD);
  const repair = (await (
    await page.request.get(`/api/v1/projects/${projectId}/repair`)
  ).json()) as { id: string };
  await post(page, base, `/api/v1/__test__/repair-proposals/${repair.id}/execute`);
  await expect(page.getByText("Zahid Mahmud")).toBeVisible(LOAD);
  await expect(page.getByText("Best fit")).toBeVisible();
  await expect(page.getByText(/Finishes .* (later|sooner)|Same finish date/)).toBeVisible();
  expect(await problems(page)).toEqual([]);
  await page.getByRole("button", { name: "Invite" }).first().click();
  await expect(page.getByText("Not sent yet").or(page.getByText("Invited")).first()).toBeVisible(
    LOAD,
  );

  // FR-INV-4: Zahid sees "selected as a replacement" and accepts; a lead is recommended.
  await zahid.page.goto("/dev");
  await expect(zahid.page.getByText("You were selected as a replacement")).toBeVisible(LOAD);
  await zahid.page.getByRole("button", { name: "Accept" }).click();
  await expect(zahid.page.getByText(/^You joined\./)).toBeVisible(LOAD);

  await page.reload();
  await expect(page.getByText(/^Recommended: /)).toBeVisible(LOAD);
  await expect(page.getByText(/Highest teamwork capacity/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Start project" })).toBeDisabled();
  await page.getByRole("button", { name: "Confirm lead" }).click();
  await expect(page.getByText(/leads the team\.$/)).toBeVisible(LOAD);

  // FR-INV-5: the client starts the project; the workspace opens on the Team tab.
  await expect(page.getByRole("button", { name: "Start project" })).toBeEnabled();
  await page.getByRole("button", { name: "Start project" }).click();
  await page
    .getByRole("alertdialog", { name: "Start the project?" })
    .getByRole("button", { name: "Start project" })
    .click();
  await page.getByRole("link", { name: "Open workspace" }).click(LOAD);
  const tabs = page.getByRole("navigation", { name: "Workspace" });
  await expect(tabs.getByText("Team", { exact: true })).toHaveAttribute(
    "aria-current",
    "page",
    LOAD,
  );
  expect(watch.consoleErrors).toEqual([]);
  expect(watch.foreign).toEqual([]);
  expect(await watch.violations()).toEqual([]);

  // A member's workspace shows nobody's price; the bell counts unread notifications.
  await sadia.page.goto(`/w/${projectId}/team`);
  await expect(sadia.page.getByText("(you)")).toBeVisible(LOAD);
  await expect(sadia.page.locator("main")).not.toContainText("৳");
  expect(await problems(sadia.page)).toEqual([]);
  await expect(
    sadia.page.getByRole("button", { name: /^Notifications, \d+ unread$/ }).first(),
  ).toBeVisible();
  await sadia.page.goto("/notifications");
  await expect(sadia.page.getByText("Project started").first()).toBeVisible(LOAD);
  expect(await problems(sadia.page)).toEqual([]);
  await sadia.page.getByRole("button", { name: "Mark all read" }).click();
  await expect(sadia.page.getByRole("button", { name: "Mark all read" })).toHaveCount(0);

  // Someone outside the team gets "not found" for the team.
  const outsider = await newDev(page, base, "Farhan Kabir");
  const denied = await outsider.page.request.get(`/api/v1/projects/${projectId}/team`);
  expect(denied.status()).toBe(404);
  await outsider.ctx.close();

  for (const d of [nadia, tanvir, sadia, imran, zahid]) await d.ctx.close();
});
