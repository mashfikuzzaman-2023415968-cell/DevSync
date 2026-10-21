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

/** Click once the page has stopped scrolling. The app scrolls smoothly (index.css), so in Firefox
 * the scroll Playwright starts to bring an element into view can still be animating when it
 * clicks, and the click lands where the element used to be. */
export async function clickSettled(target: Locator): Promise<void> {
  await target.scrollIntoViewIfNeeded();
  await target.page().waitForFunction(
    () =>
      new Promise<boolean>((resolve) => {
        const y = window.scrollY;
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            resolve(window.scrollY === y);
          });
        });
      }),
  );
  await target.click();
}
