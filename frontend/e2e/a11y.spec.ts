/** Accessibility (spec §13.6, §14.13 row 2): no serious or critical axe violations on any
 * screen, in light and dark. */
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect, resetLimits, test } from "./test";
import { apiSignIn } from "./fixtures";
import { PUBLIC_SCREENS, SIGNED_IN_SCREENS } from "./screens";

async function serious(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test("public screens have no serious accessibility violations @a11y", async ({ page }) => {
  test.setTimeout(180_000);
  const found: string[] = [];
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
    for (const s of PUBLIC_SCREENS) {
      await resetLimits(page.request);
      await page.goto(s.path);
      await page.waitForLoadState("networkidle");
      found.push(...(await serious(page)).map((v) => `${s.name} ${scheme}: ${v}`));
    }
  }
  expect(found).toEqual([]);
});

for (const role of ["DEVELOPER", "CLIENT", "ADMIN"] as const) {
  test(`${role.toLowerCase()} screens have no serious accessibility violations @a11y`, async ({
    page,
    baseURL,
  }) => {
    await apiSignIn(page, baseURL ?? "", role, "Nadia Rahman");
    const found: string[] = [];
    for (const scheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      for (const s of SIGNED_IN_SCREENS.filter((x) => x.role === role)) {
        await resetLimits(page.request);
        await page.goto(s.path);
        await page.waitForLoadState("networkidle");
        found.push(...(await serious(page)).map((v) => `${s.name} ${scheme}: ${v}`));
      }
    }
    expect(found).toEqual([]);
  });
}
