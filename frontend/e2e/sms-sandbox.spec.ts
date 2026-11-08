/**
 * The developer SMS inbox (/sandbox/sms): a real sign-up's phone code shows up there, the code
 * shown is the one that verifies the account, and the page itself is clean (CSP, axe, no
 * sideways scroll on phones). Used to present the sign-up in a demo without a phone.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./test";
import { PASSWORD, uniqueEmail, uniquePhone, watchPage } from "./fixtures";

test("the sign-up code is read from the SMS inbox and verifies the account @e2e", async ({
  page,
  baseURL,
}) => {
  const origin = new URL(baseURL ?? "https://localhost").origin;
  const phone = uniquePhone();
  await page.goto("/register?role=developer");
  await page.getByLabel("Full name").fill("Sandbox Reader");
  await page.getByLabel("Email").fill(uniqueEmail("e2e-sandbox"));
  await page.getByLabel("Mobile number").fill(phone);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByLabel(/I agree to the terms/).check();
  await page.waitForTimeout(2100); // public forms reject submissions faster than 2 s (bot check)
  await page.getByRole("button", { name: /Create account|Checking/ }).click();
  await expect(page).toHaveURL(/\/verify$/);

  // A second tab plays the presenter's second screen.
  const inbox = await page.context().newPage();
  const watch = await watchPage(inbox, origin);
  await inbox.goto("/sandbox/sms");
  await expect(inbox.getByRole("heading", { level: 1, name: "SMS inbox" })).toBeVisible();
  await inbox.getByLabel("Show texts to").fill(phone);
  const shown = inbox.getByTestId("newest-code");
  await expect(shown).toBeVisible({ timeout: 15_000 });
  const code = (await shown.textContent())?.trim() ?? "";
  expect(code).toMatch(/^\d{6}$/);
  await expect(inbox.getByText(`Your DevSync code is ${code}`)).toBeVisible();

  // The page is clean: no sideways scroll, no serious accessibility problems, CSP intact.
  const overflow = await inbox.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  const axe = await new AxeBuilder({ page: inbox }).analyze();
  expect(axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual(
    [],
  );
  expect(watch.consoleErrors).toEqual([]);
  expect(await watch.violations()).toEqual([]);
  expect(watch.foreign).toEqual([]);

  // The code from the inbox is the one that works.
  await page.bringToFront();
  await page.getByLabel("Digit 1 of 6").fill(code.charAt(0));
  await page.keyboard.type(code.slice(1));
  await page.getByRole("button", { name: "Verify phone" }).click();
  await expect(page.getByText("✓ Phone verified")).toBeVisible();

  // Clearing empties it.
  await inbox.bringToFront();
  await inbox.getByRole("button", { name: "Clear inbox" }).click();
  await expect(inbox.getByText("Inbox cleared").first()).toBeVisible();
  await expect(inbox.getByText("No texts to that number")).toBeVisible(); // filter still set
  await inbox.getByLabel("Show texts to").fill("");
  await expect(inbox.getByText("No texts yet")).toBeVisible();
});
