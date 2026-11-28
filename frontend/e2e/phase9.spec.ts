/**
 * Phase 9 end to end (spec §17 Phase 9 "E2E", the Demo 2 walkthrough §17.0): on a started
 * project the lead creates a task for a member; the member drags it with the keyboard, posts the
 * weekly check-in, comments with a mention of the lead and uploads a file; the lead finds the
 * mention in their notifications. The client watches progress — Overview, Timeline, Milestones,
 * Risks and the check-ins feed — with no drag handles or task actions, and a task move through
 * the API as the client is 403. A late critical milestone opens a CRITICAL risk with its deadline
 * impact. The board works on a phone: column tabs and the "Move to…" menu. Layout and axe run on
 * each new screen.
 *
 * The test stack runs no worker: formation and monitoring run through the test-only router.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Browser, BrowserContext, Page } from "@playwright/test";
import { csrfHeaders, watchPage } from "./fixtures";
import { layoutProblems } from "./layout-checks";
import { type Bidder, signInAsBidder, startedProject } from "./stateful-screens";
import { expect, test } from "./test";

// After a navigation a workspace tab loads several queries; a loaded laptop needs more than 5 s.
const LOAD = { timeout: 20_000 };
const ACTIVE_MILESTONE = "Requirements & design";
const TASK = "Stock list API";
const DAY_MS = 86_400_000;

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

async function person(
  browser: Browser,
  baseURL: string,
  bidders: Map<string, Bidder>,
  name: string,
): Promise<{ ctx: BrowserContext; page: Page }> {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, baseURL });
  const page = await ctx.newPage();
  await signInAsBidder(page, baseURL, bidders, name);
  return { ctx, page };
}

/** Pick `option` in the Radix select labelled `label` inside `scope`. */
async function choose(page: Page, label: string, option: string | RegExp): Promise<void> {
  await page.getByRole("combobox", { name: label }).click();
  await page.getByRole("option", { name: option }).click();
}

test("Phase 9: the team works on the board and the client watches progress @e2e", async ({
  page,
  baseURL,
  browser,
}) => {
  test.setTimeout(420_000);
  const base = baseURL ?? "";
  const origin = new URL(base).origin;
  const { projectId, bidders, lead, members } = await startedProject(page, base);
  const memberName = members.find((m) => m !== lead) ?? "";
  const leader = await person(browser, base, bidders, lead);
  const member = await person(browser, base, bidders, memberName);

  // The lead creates a task for the member in the active milestone.
  const leadWatch = await watchPage(leader.page, origin);
  await leader.page.goto(`/w/${projectId}/tasks`);
  await leader.page.getByRole("button", { name: "New task" }).first().click(LOAD);
  const form = leader.page.getByRole("dialog");
  await form.getByLabel("Title").fill(TASK);
  await choose(leader.page, "Milestone", ACTIVE_MILESTONE);
  await choose(leader.page, "Assignee", memberName);
  await form.getByLabel("Estimate (hours)").fill("8");
  await form.getByRole("button", { name: "Create task" }).click();
  const todo = leader.page.getByRole("list", { name: "To do tasks" });
  await expect(todo.getByText(TASK)).toBeVisible(LOAD);
  expect(await problems(leader.page)).toEqual([]);

  // The member drags it to In progress with the keyboard (dnd-kit's keyboard sensor).
  const memberWatch = await watchPage(member.page, origin);
  await member.page.goto(`/w/${projectId}/tasks`);
  const handle = member.page.getByRole("button", { name: `Move ${TASK}`, exact: true });
  await handle.focus(LOAD);
  await member.page.keyboard.press("Space");
  await member.page.keyboard.press("ArrowRight");
  await member.page.keyboard.press("Space");
  const doing = member.page.getByRole("list", { name: "In progress tasks" });
  await expect(doing.getByText(TASK)).toBeVisible(LOAD);

  // The member posts this week's check-in.
  await member.page.goto(`/w/${projectId}/check-ins`);
  await member.page.getByLabel(/What did you finish/).fill("Set up the stock table.", LOAD);
  await member.page.getByLabel(/What’s next/).fill("Paging and filters.");
  await member.page.getByRole("button", { name: "Post check-in" }).click();
  await expect(member.page.getByText("You checked in this week.")).toBeVisible(LOAD);
  expect(await problems(member.page)).toEqual([]);

  // The member comments on the task, mentioning the lead.
  await member.page.goto(`/w/${projectId}/tasks`);
  await member.page.getByRole("button", { name: TASK, exact: true }).click(LOAD);
  const drawer = member.page.getByRole("dialog");
  await drawer.getByRole("textbox", { name: "Write a comment" }).fill("Paging is ready to review.", LOAD);
  await drawer.getByRole("combobox", { name: "Mention someone" }).click();
  await member.page.getByRole("option", { name: lead }).click();
  await drawer.getByRole("button", { name: "Post comment" }).click();
  await expect(drawer.getByText("Paging is ready to review.")).toBeVisible(LOAD);
  await member.page.keyboard.press("Escape");

  // The member uploads a file to the project's Files.
  await member.page.goto(`/w/${projectId}/files`);
  const png = Buffer.from(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000" +
      "1f15c4890000000d49444154789c6360f8cf00000301010018dd8db00000000049454e44ae426082",
    "hex",
  );
  await member.page
    .getByLabel(/Choose a file to upload/)
    .setInputFiles({ name: "board.png", mimeType: "image/png", buffer: png });
  await expect(member.page.getByText("Uploaded board.png")).toBeVisible(LOAD);
  await expect(member.page.getByRole("link", { name: "Download board.png" })).toBeVisible();
  expect(await problems(member.page)).toEqual([]);
  expect(memberWatch.consoleErrors).toEqual([]);
  expect(await memberWatch.violations()).toEqual([]);

  // The lead finds the mention in their notifications.
  await leader.page.goto("/notifications");
  await expect(leader.page.getByText(`${memberName} mentioned you`).first()).toBeVisible(LOAD);
  expect(leadWatch.consoleErrors).toEqual([]);
  expect(await leadWatch.violations()).toEqual([]);

  // The client watches: every read-only tab opens, with no drag handles or task actions.
  const watch = await watchPage(page, origin);
  for (const [tab, check] of [
    ["overview", "Recent activity"],
    ["timeline", ACTIVE_MILESTONE],
    ["milestones", ACTIVE_MILESTONE],
    ["check-ins", "Set up the stock table."],
    ["evidence", "What each member has done"],
  ] as const) {
    await page.goto(`/w/${projectId}/${tab}`);
    await expect(page.getByText(check).first()).toBeVisible(LOAD);
    expect(await problems(page), tab).toEqual([]);
  }
  await page.goto(`/w/${projectId}/tasks`);
  await expect(page.getByText(TASK)).toBeVisible(LOAD);
  await expect(page.getByRole("button", { name: `Move ${TASK}`, exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "New task" })).toHaveCount(0);
  const tasks = (await (
    await page.request.get(`/api/v1/projects/${projectId}/tasks`)
  ).json()) as { items: { id: string; version: number }[] };
  const task = tasks.items.at(0);
  if (!task) throw new Error("no task");
  const moved = await page.request.post(`/api/v1/tasks/${task.id}/move`, {
    headers: { ...(await csrfHeaders(page.request, base)), "If-Match": String(task.version) },
    data: { status: "REVIEW" },
  });
  expect(moved.status()).toBe(403);

  // A late critical milestone: evaluated well past its planned finish, a CRITICAL risk opens
  // with the deadline impact, and the Overview's risk follows.
  const asOf = new Date(Date.now() + 30 * DAY_MS).toISOString();
  const evaluated = await page.request.post(
    `/api/v1/__test__/projects/${projectId}/monitoring/evaluate`,
    { headers: await csrfHeaders(page.request, base), data: { as_of: asOf } },
  );
  expect(evaluated.ok()).toBe(true);
  await page.goto(`/w/${projectId}/risks`);
  await expect(page.getByText("Critical").first()).toBeVisible(LOAD);
  await expect(page.getByText(/pushes the deadline by \d+ days?/).first()).toBeVisible();
  expect(await problems(page)).toEqual([]);
  expect(watch.consoleErrors).toEqual([]);
  expect(watch.foreign).toEqual([]);
  expect(await watch.violations()).toEqual([]);

  // On a phone the board shows one column with tabs, and "Move to…" moves a card.
  await member.page.setViewportSize({ width: 390, height: 844 });
  await member.page.goto(`/w/${projectId}/tasks`);
  const columns = member.page.getByRole("navigation", { name: "Board columns" });
  await expect(columns).toBeVisible(LOAD);
  await columns.getByRole("button", { name: /In progress/ }).click();
  await member.page
    .getByRole("button", { name: `Move ${TASK} to another column` })
    .click(LOAD);
  await member.page.getByRole("menuitem", { name: "Move to Review" }).click();
  await columns.getByRole("button", { name: /Review/ }).click();
  await expect(
    member.page.getByRole("list", { name: "Review tasks" }).getByText(TASK),
  ).toBeVisible(LOAD);

  await leader.ctx.close();
  await member.ctx.close();
});
