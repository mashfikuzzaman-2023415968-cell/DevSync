/** Responsive viewport matrix (spec §13.14): every built screen at five sizes, light and dark. */
import type { Page } from "@playwright/test";
import { expect, resetLimits, test } from "./test";
import { apiSignIn } from "./fixtures";
import { layoutProblems } from "./layout-checks";
import { PUBLIC_SCREENS, SIGNED_IN_SCREENS, type Screen } from "./screens";

const VIEWPORTS = [
  { width: 375, height: 667, touch: true },
  { width: 390, height: 844, touch: true },
  { width: 768, height: 1024, touch: true },
  { width: 1366, height: 768, touch: false },
  { width: 1440, height: 900, touch: false },
] as const;

async function check(page: Page, screen: Screen, results: string[]) {
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
    for (const v of VIEWPORTS) {
      await page.setViewportSize({ width: v.width, height: v.height });
      await resetLimits(page.request);
      await page.goto(screen.path);
      await page.waitForLoadState("networkidle");
      const problems = await page.evaluate(layoutProblems, { touch: v.touch });
      for (const p of problems)
        results.push(`${screen.name} ${String(v.width)}×${String(v.height)} ${scheme}: ${p}`);
    }
  }
}

test("public screens pass the viewport matrix @e2e", async ({ page }) => {
  test.setTimeout(240_000);
  const results: string[] = [];
  for (const s of PUBLIC_SCREENS) await check(page, s, results);
  expect(results).toEqual([]);
});

for (const role of ["DEVELOPER", "CLIENT", "ADMIN"] as const) {
  test(`${role.toLowerCase()} screens pass the viewport matrix @e2e`, async ({ page, baseURL }) => {
    test.setTimeout(240_000);
    await apiSignIn(page, baseURL ?? "", role, "Nadia Rahman");
    const results: string[] = [];
    for (const s of SIGNED_IN_SCREENS.filter((x) => x.role === role)) await check(page, s, results);
    expect(results).toEqual([]);
  });
}

test("mobile menu sheets pass the checks @e2e", async ({ page, baseURL }) => {
  const results: string[] = [];
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.getByRole("dialog", { name: "Menu" })).toBeVisible();
  results.push(
    ...(await page.evaluate(layoutProblems, { touch: true })).map((p) => `homepage menu: ${p}`),
  );
  await apiSignIn(page, baseURL ?? "", "DEVELOPER");
  await page.goto("/dev");
  await page
    .getByRole("navigation", { name: "Quick navigation" })
    .getByRole("button", { name: "More" })
    .click();
  await expect(page.getByRole("dialog", { name: "More" })).toBeVisible();
  results.push(
    ...(await page.evaluate(layoutProblems, { touch: true })).map((p) => `more sheet: ${p}`),
  );
  expect(results).toEqual([]);
});
