/** No CSP violations, console errors or off-origin requests on any screen (spec §14.3 CSP
 * spike, §14.13 row 2). */
import { expect, resetLimits, test } from "./test";
import { apiSignIn, watchPage } from "./fixtures";
import { PUBLIC_SCREENS, SIGNED_IN_SCREENS } from "./screens";

test("public screens: strict CSP holds, no console errors, nothing off-origin @e2e", async ({
  page,
  baseURL,
}) => {
  const origin = new URL(baseURL ?? "https://localhost").origin;
  const w = await watchPage(page, origin);
  for (const s of PUBLIC_SCREENS) {
    await resetLimits(page.request);
    await page.goto(s.path);
    await page.waitForLoadState("networkidle");
    // Open the overlays that add styles at runtime (Radix scroll lock uses the style nonce).
    if (s.name === "homepage") {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.getByRole("button", { name: "Open menu" }).click();
      await page.keyboard.press("Escape");
      await page.setViewportSize({ width: 1280, height: 720 });
    }
    expect(await w.violations(), s.name).toEqual([]);
  }
  expect(w.consoleErrors).toEqual([]);
  expect(w.foreign).toEqual([]);
});

for (const role of ["DEVELOPER", "CLIENT", "ADMIN"] as const) {
  test(`${role.toLowerCase()} screens: strict CSP holds with dialogs and menus open @e2e`, async ({
    page,
    baseURL,
  }) => {
    const origin = new URL(baseURL ?? "https://localhost").origin;
    const w = await watchPage(page, origin);
    await apiSignIn(page, baseURL ?? "", role, "Nadia Rahman");
    for (const s of SIGNED_IN_SCREENS.filter((x) => x.role === role)) {
      await page.goto(s.path);
      await page.waitForLoadState("networkidle");
      await page.getByRole("button", { name: "Account menu" }).click();
      await page.keyboard.press("Escape");
      await page.keyboard.press("Control+k");
      await page.keyboard.press("Escape");
      expect(await w.violations(), s.name).toEqual([]);
    }
    expect(w.consoleErrors).toEqual([]);
    expect(w.foreign).toEqual([]);
  });
}
