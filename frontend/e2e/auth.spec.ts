/** Phase 1 end-to-end flows (spec §17 Phase 1 tests). */
import { expect, test } from "@playwright/test";
import {
  lastLink,
  lastSms,
  PASSWORD,
  seedUser,
  signIn,
  totpNow,
  uniqueEmail,
  uniquePhone,
} from "./fixtures";

test.describe.configure({ mode: "serial" });

test("homepage links into registration with the role preselected @e2e", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Hire a team" }).click();
  await expect(page).toHaveURL(/\/register\?role=client/);
  await expect(page.getByRole("heading", { name: "Your details" })).toBeVisible();
  await expect(page.getByText("You’re signing up to hire a team.")).toBeVisible();
});

test("register, verify phone and email, land on the role home @e2e", async ({
  page,
  request,
  baseURL,
}) => {
  const email = uniqueEmail("e2e-dev");
  const phone = uniquePhone();
  await page.goto("/register?role=developer");
  await page.getByLabel("Full name").fill("Nadia Rahman");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mobile number").fill(phone);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByLabel(/I agree to the terms/).check();
  await page.waitForTimeout(2100); // public forms reject submissions faster than 2 s (bot check)
  await page.getByRole("button", { name: /Create account|Checking/ }).click();
  await expect(page).toHaveURL(/\/verify$/);

  const code = await lastSms(request, phone);
  expect(code).toMatch(/^\d{6}$/);
  await page.getByLabel("Digit 1 of 6").fill(code.charAt(0));
  await page.keyboard.type(code.slice(1));
  await page.getByRole("button", { name: "Verify phone" }).click();
  await expect(page.getByText("✓ Phone verified")).toBeVisible();

  const link = await lastLink(request, email, "verify_email");
  const path = new URL(link).pathname + new URL(link).search;
  await page.goto(path);
  await expect(page.getByText("Your email is verified.")).toBeVisible();
  await page.getByRole("link", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/dev$/);
  await expect(page.getByRole("heading", { name: "Hello, Nadia Rahman" })).toBeVisible();
  expect(baseURL).toBeTruthy();
});

test("repeated wrong passwords are throttled with a wait time @e2e", async ({
  page,
  request,
  baseURL,
}) => {
  const user = await seedUser(request, baseURL ?? "", "CLIENT");
  for (let i = 0; i < 6; i += 1) {
    await signIn(page, user.email, "a wrong password 123");
    await expect(page.getByRole("alert")).toBeVisible();
  }
  await expect(page.getByRole("alert")).toContainText(/Try again in \d+ (seconds|minutes)/);
});

test("admin sign-in requires TOTP @e2e", async ({ page, request, baseURL }) => {
  const admin = await seedUser(request, baseURL ?? "", "ADMIN");
  await signIn(page, admin.email, admin.password);
  await expect(page).toHaveURL(/\/login\/totp$/);
  const code = await totpNow(request, admin.totpSecret ?? "");
  await page.getByLabel("Digit 1 of 6").fill(code.charAt(0));
  await page.keyboard.type(code.slice(1));
  await page.getByRole("button", { name: "Verify and sign in" }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole("heading", { name: "Administration" })).toBeVisible();
});

test("signing out of every device ends the other browser's session @e2e", async ({
  browser,
  request,
  baseURL,
}) => {
  const user = await seedUser(request, baseURL ?? "", "DEVELOPER");
  const first = await browser.newContext({ ignoreHTTPSErrors: true, baseURL: baseURL ?? "" });
  const second = await browser.newContext({ ignoreHTTPSErrors: true, baseURL: baseURL ?? "" });
  const a = await first.newPage();
  const b = await second.newPage();
  await signIn(a, user.email, user.password);
  await expect(a).toHaveURL(/\/dev$/);
  await signIn(b, user.email, user.password);
  await expect(b).toHaveURL(/\/dev$/);
  await a.goto("/settings");
  await a.getByRole("button", { name: "Sign out of every device" }).click();
  await expect(a).toHaveURL(/\/$/);
  await b.goto("/settings");
  await expect(b).toHaveURL(/\/login\?return_to=%2Fsettings$/);
  await first.close();
  await second.close();
});

test("non-admins never download the admin bundle @e2e", async ({ page, request, baseURL }) => {
  const client = await seedUser(request, baseURL ?? "", "CLIENT");
  const requested: string[] = [];
  page.on("request", (r) => requested.push(r.url()));
  await signIn(page, client.email, client.password);
  await expect(page).toHaveURL(/\/client$/);
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/client$/);
  expect(requested.filter((u) => /AdminHome/.test(u))).toEqual([]);
});
