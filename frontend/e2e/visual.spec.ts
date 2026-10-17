/**
 * Visual baselines (spec §13.14 #2, §16.5 step 15): homepage, auth screens, the app shell and
 * the Phase 3 profile and challenge screens,
 * light and dark, at 390, 768 and 1440 px. Rendered with reduced motion (final states, poster
 * instead of the live scene) and a fixed clock so they are stable.
 * Update with `make visual-update` (runs in the pinned Playwright image).
 */
import type { Page } from "@playwright/test";
import { expect, resetLimits, test } from "./test";
import { apiSignIn } from "./fixtures";

const WIDTHS = [390, 768, 1440] as const;
const FIXED_NOW = new Date("2026-10-12T04:00:00Z"); // 10:00 in Dhaka → "Good morning"

async function prepare(page: Page, scheme: "light" | "dark", width: number) {
  await page.clock.setFixedTime(FIXED_NOW);
  await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
  await page.setViewportSize({ width, height: 900 });
}

async function snap(page: Page, name: string, mask: string[] = []) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot(`${name}.png`, {
    fullPage: true,
    animations: "disabled",
    caret: "hide",
    mask: mask.map((m) => page.locator(m)),
  });
}

for (const scheme of ["light", "dark"] as const) {
  for (const width of WIDTHS) {
    test(`public screens ${scheme} ${String(width)} @visual`, async ({ page }) => {
      await prepare(page, scheme, width);
      // Homepage: the first screen plus each section on its own. A full-page capture stretches the
      // viewport, which distorts the scroll-driven "How it works" section (sized in vh).
      await resetLimits(page.request);
      await page.goto("/");
      await page.waitForLoadState("networkidle");
      await page.evaluate(() => document.fonts.ready);
      await expect(page).toHaveScreenshot(`homepage-${scheme}-${String(width)}.png`, {
        animations: "disabled",
        mask: [page.locator("[data-volatile]")],
      });
      for (const section of [
        "#features",
        "#for-clients",
        "#fairness",
        "#research",
        "#faq",
        "footer",
      ]) {
        const el = page.locator(
          section === "#for-clients" ? "section[aria-labelledby=audience-title]" : section,
        );
        await el.scrollIntoViewIfNeeded();
        await expect(el).toHaveScreenshot(
          `homepage-${section.replace("#", "")}-${scheme}-${String(width)}.png`,
          {
            animations: "disabled",
            // The sticky navbar and back-to-top button float over sections depending on scroll.
            mask: [
              page.locator("main").locator("xpath=preceding-sibling::header"),
              page.getByRole("button", { name: "Back to top" }),
            ],
          },
        );
      }
      for (const [name, path] of [
        ["login", "/login"],
        ["register", "/register"],
        ["register-details", "/register?role=client"],
        ["not-found", "/missing"],
      ] as const) {
        await resetLimits(page.request);
        await page.goto(path);
        await snap(page, `${name}-${scheme}-${String(width)}`);
      }
    });

    test(`app shell ${scheme} ${String(width)} @visual`, async ({ page, baseURL }) => {
      await prepare(page, scheme, width);
      await apiSignIn(page, baseURL ?? "", "DEVELOPER", "Nadia Rahman");
      await page.goto("/dev");
      await snap(page, `developer-home-${scheme}-${String(width)}`);
      await page.goto("/settings");
      // The email and the device list change on every run.
      await snap(page, `settings-${scheme}-${String(width)}`, ["[data-volatile]"]);
      await page.goto("/dev/profile");
      await page.getByLabel("Headline").waitFor();
      await snap(page, `developer-profile-${scheme}-${String(width)}`);
      await page.goto("/dev/challenges");
      await page.getByRole("heading", { name: "React skill test" }).waitFor();
      await snap(page, `skill-challenges-${scheme}-${String(width)}`);
    });
  }
}
