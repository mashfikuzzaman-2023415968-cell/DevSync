/** App shell per role (spec §13.4, §17 Phase 2 tests). */
import { expect, mainNav, test } from "./test";
import { apiSignIn } from "./fixtures";

test("each role sees its own navigation and pages @e2e", async ({ page, baseURL }) => {
  await apiSignIn(page, baseURL ?? "", "DEVELOPER");
  await page.goto("/dev");
  // "Find projects" is a sidebar item on desktop and the "Find work" tab on phones.
  await expect(
    page
      .getByRole("link", { name: /^(Find projects|Find work)$/ })
      .filter({ visible: true })
      .first(),
  ).toBeVisible();
  const nav = await mainNav(page);
  await nav.getByRole("link", { name: "Reputation" }).click();
  await expect(page).toHaveURL(/\/dev\/reputation$/);
  await expect(page.getByRole("heading", { level: 1, name: "Reputation" })).toBeVisible();
  await expect(page.getByText("Reputation arrives in Phase 6")).toBeVisible();
  await expect(page).toHaveTitle("Reputation · DevSync");
  await page.goto("/client");
  await expect(page).toHaveURL(/\/403$/);
});

test("client navigation and the admin area hidden from them @e2e", async ({ page, baseURL }) => {
  await apiSignIn(page, baseURL ?? "", "CLIENT");
  await page.goto("/client");
  await expect((await mainNav(page)).getByRole("link", { name: "Create project" })).toBeVisible();
  await page.goto("/admin");
  await expect(page).not.toHaveURL(/\/admin$/);
});

test("admin shell after two-step sign-in @e2e", async ({ page, baseURL }) => {
  await apiSignIn(page, baseURL ?? "", "ADMIN", "Admin");
  await page.goto("/admin");
  await expect(page.getByRole("heading", { level: 1, name: "Administration" })).toBeVisible();
  await expect((await mainNav(page)).getByRole("link", { name: "Audit log" })).toBeVisible();
});

test("sidebar collapse persists across reloads @e2e", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await apiSignIn(page, baseURL ?? "", "DEVELOPER");
  await page.goto("/dev");
  const aside = page.getByRole("complementary", { name: "Main navigation" });
  const wide = (await aside.boundingBox())?.width ?? 0;
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect.poll(async () => (await aside.boundingBox())?.width ?? 0).toBeLessThan(80);
  await page.reload();
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
  expect(wide).toBeGreaterThan(240);
});

test("command palette opens with the keyboard @e2e", async ({ page, baseURL }) => {
  await apiSignIn(page, baseURL ?? "", "DEVELOPER");
  await page.goto("/dev");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.keyboard.press("Control+k");
  await page.getByPlaceholder("Go to a page or run an action…").fill("settings");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/settings$/);
});

test("phones get the bottom tab bar and the More sheet @e2e", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await apiSignIn(page, baseURL ?? "", "DEVELOPER");
  await page.goto("/dev");
  await expect(page.getByRole("complementary", { name: "Main navigation" })).toBeHidden();
  const tabs = page.getByRole("navigation", { name: "Quick navigation" });
  await tabs.getByRole("button", { name: "More" }).click();
  const sheet = page.getByRole("dialog", { name: "More" });
  await sheet.getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(sheet).toBeHidden();
});

test("homepage menu opens as a full-height sheet on phones @e2e", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open menu" }).click();
  const menu = page.getByRole("dialog", { name: "Menu" });
  await expect(menu.getByRole("link", { name: "Browse projects" })).toBeVisible();
  await menu.getByRole("link", { name: "Get started" }).click();
  await expect(page).toHaveURL(/\/register$/);
});
