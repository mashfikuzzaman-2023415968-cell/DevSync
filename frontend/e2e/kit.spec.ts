/**
 * The development-only UI kit (spec §17 Phase 2 #9): every component and state, light and
 * dark, at desktop and phone width, with zero CSP violations. Runs against a separate
 * dev-tools build served on KIT_URL; production builds never contain the kit.
 */
import { expect, test } from "./test";
import { watchPage } from "./fixtures";

const KIT = process.env.KIT_URL;
test.skip(!KIT, "KIT_URL not set (the gate serves the dev-tools build)");

for (const scheme of ["light", "dark"] as const) {
  for (const width of [390, 1440] as const) {
    test(`UI kit ${scheme} ${String(width)} @visual`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`${KIT ?? ""}/dev/ui-kit`);
      await expect(page.getByRole("heading", { level: 1, name: "UI kit" })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await expect(page).toHaveScreenshot(`ui-kit-${scheme}-${String(width)}.png`, {
        fullPage: true,
        animations: "disabled",
        caret: "hide",
      });
    });
  }
}

test("UI kit overlays respect the strict CSP @visual", async ({ page }) => {
  const w = await watchPage(page, new URL(KIT ?? "http://127.0.0.1").origin);
  await page.goto(`${KIT ?? ""}/dev/ui-kit`);
  for (const name of ["Open dialog", "Open sheet", "Menu", "Popover"]) {
    await page.getByRole("button", { name, exact: true }).click();
    await page.keyboard.press("Escape");
  }
  await page.getByRole("button", { name: "Show toast" }).click();
  await page.getByRole("combobox").first().click();
  await page.keyboard.press("Escape");
  expect(await w.violations()).toEqual([]);
  expect(w.consoleErrors).toEqual([]);
});
