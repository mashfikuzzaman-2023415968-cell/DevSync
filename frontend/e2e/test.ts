/**
 * Shared Playwright `test`: before every test, clear the API's rate-limit counters through the
 * test-only router (DEVSYNC_ENV=test). All E2E traffic comes from one container IP, so without
 * this, independent tests would throttle each other under the real per-IP limits (§14.8).
 */
import { test as base, type APIRequestContext, type Locator, type Page } from "@playwright/test";

export async function resetLimits(request: APIRequestContext): Promise<void> {
  const r = await request.get("/api/v1/__test__/ratelimits/reset");
  if (r.status() !== 204) throw new Error(`rate-limit reset failed: ${String(r.status())}`);
}

export const test = base.extend<{ freshLimits: undefined }>({
  // The app scrolls smoothly (index.css). When Playwright scrolls an element into view to click
  // it, Firefox and WebKit can still be animating, so the click lands where the element used to
  // be and is lost (D53). Tests turn the animation off; nothing asserts on scroll motion.
  page: async ({ page }, provide) => {
    await page.addInitScript(() => {
      // The <html> element may not exist yet (WebKit) or be replaced (Firefox) when this runs,
      // so set it again once the page is parsed.
      const off = () => {
        const root = document.documentElement as HTMLElement | null;
        if (root) root.style.scrollBehavior = "auto";
      };
      document.addEventListener("DOMContentLoaded", off);
      off();
    });
    await provide(page);
  },
  freshLimits: [
    async ({ request }, use) => {
      await resetLimits(request);
      await use(undefined);
    },
    { auto: true },
  ],
});

export { expect } from "@playwright/test";

/** The role navigation: the sidebar on desktop and tablet, or the "More" sheet behind the bottom
 * tab bar on phones (spec §13.14). Returns the region whose links the test can click. */
export async function mainNav(page: Page): Promise<Locator> {
  const sidebar = page.getByRole("complementary", { name: "Main navigation" });
  if ((page.viewportSize()?.width ?? 1280) >= 768) return sidebar; // sidebar or rail
  await page
    .getByRole("navigation", { name: "Quick navigation" })
    .getByRole("button", { name: "More" })
    .click();
  return page.getByRole("dialog", { name: "More" });
}
