/**
 * Phase 0 smoke: the placeholder loads through Nginx over HTTPS with the strict
 * CSP, no console errors, no CSP violations and no requests to other origins.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("home page loads securely through the edge @e2e", async ({ page, baseURL }) => {
  const origin = new URL(baseURL ?? "https://localhost").origin;
  const consoleErrors: string[] = [];
  const foreignRequests: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (url.protocol.startsWith("http") && url.origin !== origin) foreignRequests.push(req.url());
  });
  await page.addInitScript(() => {
    (window as unknown as { __csp: string[] }).__csp = [];
    document.addEventListener("securitypolicyviolation", (e) => {
      (window as unknown as { __csp: string[] }).__csp.push(
        `${e.violatedDirective} ${e.blockedURI}`,
      );
    });
  });

  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  const headers = response?.headers() ?? {};
  expect(headers["content-security-policy"]).toContain("script-src 'self'");
  expect(headers["strict-transport-security"]).toContain("max-age=31536000");

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const fontFamily = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
  expect(fontFamily).toContain("Inter");

  const violations = await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp);
  expect(violations).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect(foreignRequests).toEqual([]);
});

test("home page has no serious accessibility violations @a11y", async ({ page }) => {
  await page.goto("/");
  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  expect(serious).toEqual([]);
});
