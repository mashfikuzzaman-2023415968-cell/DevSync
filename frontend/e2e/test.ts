/**
 * Shared Playwright `test`: before every test, clear the API's rate-limit counters through the
 * test-only router (DEVSYNC_ENV=test). All E2E traffic comes from one container IP, so without
 * this, independent tests would throttle each other under the real per-IP limits (§14.8).
 */
import {
  test as base,
  expect,
  type APIRequestContext,
  type Locator,
  type Page,
} from "@playwright/test";

export async function resetLimits(request: APIRequestContext): Promise<void> {
  const r = await request.get("/api/v1/__test__/ratelimits/reset");
  if (r.status() !== 204) throw new Error(`rate-limit reset failed: ${String(r.status())}`);
}

/**
 * The app scrolls smoothly (index.css). When Playwright scrolls an element into view to click it,
 * Firefox and WebKit can still be animating, so the click lands where the element used to be and
 * is lost (D53). Tests turn the animation off — the fixture's page, and any page a test opens in
 * a context of its own; nothing asserts on scroll motion.
 */
export async function noSmoothScroll(page: Page): Promise<void> {
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
}

export const test = base.extend<{ freshLimits: undefined }>({
  page: async ({ page }, provide) => {
    await noSmoothScroll(page);
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

/** Close a dialog or sheet with its own Close button and wait until it has gone. Escape depends
 * on where focus is, and in WebKit it was sometimes lost after the window was resized. */
/** After choosing an option in a select: wait until its list is gone and it has handed focus
 * back to its trigger (a moment later, in a timer). Filling the next field before that loses
 * the text in Firefox, because focus jumps back to the select mid-fill. */
export async function optionChosen(page: Page): Promise<void> {
  await expect(page.getByRole("listbox")).toHaveCount(0);
  await page.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => setTimeout(resolve, 0))),
  );
}

export async function closeDialog(page: Page, name: string): Promise<void> {
  const dialog = page.getByRole("dialog", { name });
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
}
