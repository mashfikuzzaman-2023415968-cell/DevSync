/**
 * Phase 6 end to end (spec §17 Phase 6 manual check, §13.5 #16): the Reputation page of an
 * experienced developer (computed from simulated histories) and of a newcomer read sensibly,
 * the charts have table alternatives and keyboard access, values are labelled as simulated, and
 * another user sees the same public reputation on the API but never the history.
 */
import { addReputationHistory, apiSignIn } from "./fixtures";
import { expect, test } from "./test";

test.describe("reputation", () => {
  test("an experienced developer sees computed values and why they changed @e2e", async ({
    page,
    baseURL,
  }) => {
    const dev = await apiSignIn(page, baseURL ?? "", "DEVELOPER", "Arif Hossain");
    await addReputationHistory(page.request, baseURL ?? "", dev.userId, 6);
    await page.goto("/dev/reputation");
    await expect(page.getByRole("heading", { level: 1, name: "Your reputation" })).toBeVisible();
    await expect(
      page.getByText(/^Based on 6 completed projects for \d+ clients?\.$/),
    ).toBeVisible();
    await expect(page.getByText("Simulated history").first()).toBeVisible();
    await expect(page.getByRole("progressbar")).toHaveCount(6);
    // Six parameters with plain labels, no paper symbols outside the drawer.
    const meters = page.getByRole("progressbar");
    for (const label of [
      "Expertise",
      "Communication",
      "Teamwork",
      "Quality",
      "Client diversity",
      "Punctuality",
    ]) {
      const names = await meters.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")));
      expect(names.some((n) => n?.startsWith(`${label} `) && n.endsWith(" of 100"))).toBe(true);
    }
    const why = page.locator("[data-card]").filter({ hasText: "Why did this change?" });
    await expect(why.getByRole("heading", { level: 3 }).first()).toHaveText("Simulated project 6");
    await expect(why.getByText(/^Punctuality /).first()).toBeVisible();
    await expect(page.locator("main")).not.toContainText(/[ωβμ]|Eq\./);
    // The trend chart: keyboard focus shows a project's values; the table shows the same.
    const trend = page.locator("[data-card]").filter({ hasText: "Trend over your projects" });
    await trend.getByRole("img", { name: /^Simulated project 1/ }).focus();
    await expect(
      trend.getByText(/^Simulated project 1 \(.+\): Competency \d+, Performance \d+$/),
    ).toBeVisible();
    await trend.getByRole("radio", { name: "View as table" }).click();
    await expect(trend.getByRole("table").getByRole("row")).toHaveCount(7);
  });

  test("a newcomer sees where the starting values come from @e2e", async ({ page, baseURL }) => {
    await apiSignIn(page, baseURL ?? "", "DEVELOPER", "Nadia Rahman");
    await page.goto("/dev/reputation");
    await expect(page.getByText("You’re a newcomer: 0 of 3 projects done.")).toBeVisible();
    await expect(page.getByText("Where your starting values come from")).toBeVisible();
    await expect(page.getByText("No completed projects yet")).toBeVisible();
    await expect(page.getByText("Simulated history")).toHaveCount(0);
  });

  test("others see the public value but never the history @e2e", async ({ page, baseURL }) => {
    const dev = await apiSignIn(page, baseURL ?? "", "DEVELOPER", "Arif Hossain");
    await addReputationHistory(page.request, baseURL ?? "", dev.userId, 3);
    const own: unknown = await (
      await page.request.get(`/api/v1/developers/${dev.userId}/reputation`)
    ).json();
    await apiSignIn(page, baseURL ?? "", "CLIENT", "Rahim Uddin");
    const seen = await page.request.get(`/api/v1/developers/${dev.userId}/reputation`);
    expect(seen.status()).toBe(200);
    expect(await seen.json()).toEqual(own);
    expect((await page.request.get("/api/v1/me/reputation/history")).status()).toBe(403);
  });
});
