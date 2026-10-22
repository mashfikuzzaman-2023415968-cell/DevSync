/**
 * Visual baselines (spec §13.14 #2, §16.5 step 15): homepage, auth screens, the app shell and
 * the Phase 3 profile and challenge screens, the Phase 4 planning screens and the Phase 5 bid
 * sheet and client Bids screen (with its "Why?" panel),
 * light and dark, at 390, 768 and 1440 px. Rendered with reduced motion (final states, poster
 * instead of the live scene) and a fixed clock so they are stable.
 * Update with `make visual-update` (runs in the pinned Playwright image).
 */
import type { Page } from "@playwright/test";
import { expect, resetLimits, test } from "./test";
import { addSkillEvidence, apiSignIn, createOrderingProject, setReputation } from "./fixtures";

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

    test(`client planning ${scheme} ${String(width)} @visual`, async ({ page, baseURL }) => {
      await prepare(page, scheme, width);
      await apiSignIn(page, baseURL ?? "", "CLIENT", "Rahim Uddin");
      await page.goto("/client/projects");
      await page.getByText("No projects yet").waitFor();
      await snap(page, `client-projects-empty-${scheme}-${String(width)}`);
      await page.goto("/client/projects/new");
      await page.getByLabel("Project title").waitFor();
      await snap(page, `create-project-${scheme}-${String(width)}`);
      const id = await createOrderingProject(page, baseURL ?? "");
      await page.goto(`/client/projects/${id}/plan`);
      await page.getByLabel("Frontend: days 4–13, slack 4 days").waitFor();
      await snap(page, `project-plan-${scheme}-${String(width)}`);
    });

    test(`bidding ${scheme} ${String(width)} @visual`, async ({ page, browser, baseURL }) => {
      const base = baseURL ?? "";
      await prepare(page, scheme, width);
      await apiSignIn(page, base, "CLIENT", "Rahim Uddin");
      const id = await createOrderingProject(page, base, { publish: true });

      // Two developers bid in their own contexts: a newcomer with an 85% React test and an
      // experienced developer who is too slow for the deadline.
      for (const [name, skill, price, days, experienced] of [
        ["Nadia Rahman", "React", "18000", "20", false],
        ["Shakib Hasan", "Testing", "18000", "31", true],
      ] as const) {
        const ctx = await browser.newContext({ ignoreHTTPSErrors: true, baseURL: base });
        const dev = await ctx.newPage();
        const user = await apiSignIn(dev, base, "DEVELOPER", name);
        await addSkillEvidence(dev.request, base, user.userId, skill, 0.85);
        if (experienced) await setReputation(dev.request, base, user.userId, 0.56, 0.59);
        await dev.goto(`/dev/projects/${id}`);
        await dev.getByRole("combobox").click();
        await dev.getByRole("option", { name: skill }).first().click();
        await dev.getByLabel(/Your price/).fill(price);
        await dev.getByLabel(/Days you need/).fill(days);
        await dev.getByRole("button", { name: "Place sealed bid" }).click();
        await dev.getByText("Bid placed").first().waitFor();
        await ctx.close();
      }

      // The bid sheet with its live eligibility preview, for a third developer.
      const ctx = await browser.newContext({ ignoreHTTPSErrors: true, baseURL: base });
      const sheet = await ctx.newPage();
      await prepare(sheet, scheme, width);
      const third = await apiSignIn(sheet, base, "DEVELOPER", "Tanvir Ahmed");
      await addSkillEvidence(sheet.request, base, third.userId, "FastAPI", 0.8);
      await sheet.goto(`/dev/projects/${id}`);
      await sheet.getByRole("combobox").click();
      await sheet.getByRole("option", { name: "FastAPI" }).first().click();
      await sheet.getByLabel(/Your price/).fill("22000");
      await sheet.getByLabel(/Days you need/).fill("18");
      await sheet.getByText("You meet every requirement.").waitFor();
      await snap(sheet, `bid-sheet-${scheme}-${String(width)}`);
      await ctx.close();

      await page.goto(`/client/projects/${id}/bids`);
      await page.getByText("Not enough eligible bids yet").waitFor();
      await snap(page, `client-bids-${scheme}-${String(width)}`, ["[data-volatile]"]);
      await page
        .getByRole("button", { name: "Why eligible: Nadia Rahman" })
        .filter({ visible: true })
        .click();
      await page.getByText("How the filter decided").waitFor();
      const panel = page.getByRole("dialog", { name: "Nadia Rahman" });
      await expect(panel).toHaveScreenshot(`why-panel-${scheme}-${String(width)}.png`, {
        animations: "disabled",
        mask: [panel.locator("[data-volatile]")],
      });
    });
  }
}
