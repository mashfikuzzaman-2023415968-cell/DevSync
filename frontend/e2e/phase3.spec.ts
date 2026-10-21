/**
 * Phase 3 flows (spec §17 Phase 3 tests): a developer completes the profile with a portfolio
 * image (downloaded through Nginx without its GPS data), takes a skill test and sees the score
 * on the public profile; a client edits their organisation; visibility is respected. Plus the
 * CSP, axe and layout checks for screens that need an object id.
 */
import AxeBuilder from "@axe-core/playwright";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";
import { clickSettled, expect, resetLimits, test } from "./test";
import { apiSignIn, watchPage } from "./fixtures";
import { layoutProblems } from "./layout-checks";

const PHOTO = fileURLToPath(new URL("./files/gps-photo.jpg", import.meta.url));

async function serious(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function checkScreen(page: Page, name: string) {
  const found: string[] = [];
  for (const [width, height, touch] of [
    [375, 667, true],
    [768, 1024, true],
    [1440, 900, false],
  ] as const) {
    await page.setViewportSize({ width, height });
    await page.waitForTimeout(150);
    const problems = await page.evaluate(layoutProblems, { touch });
    found.push(...problems.map((p) => `${name} ${String(width)}: ${p}`));
  }
  await page.setViewportSize({ width: 1280, height: 800 });
  found.push(...(await serious(page)).map((v) => `${name} axe: ${v}`));
  return found;
}

test("developer completes a profile with an image, takes a test and sees the score @e2e", async ({
  page,
  baseURL,
}) => {
  test.setTimeout(120_000);
  const origin = new URL(baseURL ?? "https://localhost").origin;
  const w = await watchPage(page, origin);
  const dev = await apiSignIn(page, baseURL ?? "", "DEVELOPER", "Nadia Rahman");

  // Profile basics autosave.
  await page.goto("/dev/profile");
  await page.getByLabel("Headline").fill("Accessible React forms");
  await expect(page.getByText("Saved", { exact: true })).toBeVisible({ timeout: 10_000 });
  await page.getByRole("checkbox", { name: "React" }).click();
  await expect(page.getByRole("radiogroup", { name: "React level" })).toBeVisible();

  // Portfolio item with an image.
  await page.getByRole("button", { name: "Add a portfolio item" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a portfolio item" });
  await dialog.getByLabel("Title").fill("Clinic booking app");
  await dialog.getByRole("button", { name: "Add item" }).click();
  const edit = page.getByRole("dialog", { name: "Edit portfolio item" });
  await edit.getByLabel(/Add an image/).setInputFiles(PHOTO);
  await expect(edit.getByRole("img", { name: "Clinic booking app, screenshot 1" })).toBeVisible({
    timeout: 15_000,
  });
  await edit.getByRole("button", { name: "Close" }).first().click();
  await expect(page.getByText("1 image")).toBeVisible();

  // The stored image comes back through Nginx without EXIF/GPS and with safe headers.
  const portfolio = (await (await page.request.get("/api/v1/me/portfolio")).json()) as {
    images: { file: { id: string } }[];
  }[];
  const fileId = portfolio[0]?.images[0]?.file.id ?? "";
  const download = await page.request.get(`/api/v1/files/${fileId}/download`);
  expect(download.status()).toBe(200);
  const headers = download.headers();
  expect(headers["content-type"]).toBe("image/jpeg");
  expect(headers["content-disposition"]).toMatch(/^attachment/);
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["content-security-policy"]).toContain("sandbox");
  const bytes = await download.body();
  expect(bytes.subarray(0, 2).toString("hex")).toBe("ffd8");
  expect(bytes.includes(Buffer.from("Exif\0\0"))).toBe(false);
  expect(bytes.includes(Buffer.from("E2E PhoneMaker"))).toBe(false);

  // Take the React test: pick the first option everywhere, then submit.
  await page.goto("/dev/challenges");
  const card = page.getByRole("group", { name: "React skill test" });
  await card.getByRole("button", { name: "Start test" }).click();
  await page.getByRole("button", { name: "Start the timer" }).click();
  await expect(page).toHaveURL(/\/dev\/challenges\/test\//, { timeout: 15_000 });
  await expect(page.getByText("Question 1 of 10")).toBeVisible();
  const csp = await checkScreen(page, "timed-test");
  for (let i = 0; i < 10; i += 1) {
    await page.getByRole("radio").first().click();
    await expect(
      page.getByRole("progressbar", { name: `${String(i + 1)} of 10 answered` }),
    ).toBeVisible();
    if (i < 9) await page.getByRole("button", { name: "Next question" }).click();
  }
  await page.getByRole("button", { name: "Submit test" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Submit test" }).click();
  await expect(page.getByText(/of 10 correct/)).toBeVisible();
  await expect(page.getByText("Added to your profile as a verified score.")).toBeVisible();

  // The public profile shows the verified score and the image.
  await page.goto(`/d/${dev.userId}`);
  await expect(page.getByRole("heading", { level: 1, name: "Nadia Rahman" })).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "React test score" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Clinic booking app, screenshot" })).toBeVisible();
  csp.push(...(await checkScreen(page, "public-profile")));
  expect(csp).toEqual([]);
  expect(await w.violations()).toEqual([]);
  expect(w.consoleErrors).toEqual([]);
  expect(w.foreign).toEqual([]);
});

test("a clients-only profile is hidden from visitors and shown to clients @e2e", async ({
  page,
  browser,
  baseURL,
}) => {
  const dev = await apiSignIn(page, baseURL ?? "", "DEVELOPER", "Hidden Dev");
  await page.goto("/dev/profile");
  // Wait for every card to load: a card arriving mid-click moves the radio and the click is lost.
  await expect(page.locator(".skeleton")).toHaveCount(0);
  const clientsOnly = page.getByRole("radio", { name: /Clients only/ });
  await clickSettled(clientsOnly);
  await expect(clientsOnly).toBeChecked();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible({ timeout: 10_000 });

  const visitor = await browser.newContext({ ignoreHTTPSErrors: true, baseURL: baseURL ?? "" });
  const anon = await visitor.newPage();
  await resetLimits(anon.request);
  await anon.goto(`/d/${dev.userId}`);
  await expect(anon.getByText("This profile isn’t available")).toBeVisible();
  await expect(anon.getByRole("link", { name: "Sign in as a client" })).toBeVisible();
  await visitor.close();

  const clientCtx = await browser.newContext({ ignoreHTTPSErrors: true, baseURL: baseURL ?? "" });
  const client = await clientCtx.newPage();
  await apiSignIn(client, baseURL ?? "", "CLIENT", "Rahim Uddin");
  await client.goto(`/d/${dev.userId}`);
  await expect(client.getByRole("heading", { level: 1, name: "Hidden Dev" })).toBeVisible();
  await clientCtx.close();
});

test("a client edits their organisation in Settings @e2e", async ({ page, baseURL }) => {
  await apiSignIn(page, baseURL ?? "", "CLIENT", "Rahim Uddin");
  await page.goto("/settings");
  await page.getByLabel("Organisation").fill("Rahim Traders");
  await page.getByLabel("What you do").fill("Wholesale textiles; we need an ordering app.");
  await page.getByLabel("Website").fill("http://example.com");
  await clickSettled(page.getByRole("button", { name: "Save organisation" }));
  await expect(page.getByText("Use a full https:// address.")).toBeVisible();
  await page.getByLabel("Website").fill("https://example.com");
  await page.getByRole("button", { name: "Save organisation" }).click();
  await expect(page.getByText("Organisation saved").first()).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Organisation")).toHaveValue("Rahim Traders");
});

test("a crafted polyglot upload is refused with a clear message @e2e", async ({
  page,
  baseURL,
}) => {
  await apiSignIn(page, baseURL ?? "", "DEVELOPER", "Nadia Rahman");
  const headers = { Origin: new URL(baseURL ?? "https://localhost").origin };
  const csrf = await page.request.get("/api/v1/auth/csrf");
  expect(csrf.status()).toBe(204);
  const token =
    (await page.context().cookies()).find((c) => c.name === "__Host-ds_csrf")?.value ?? "";
  const item = await page.request.post("/api/v1/me/portfolio", {
    headers: { ...headers, "X-CSRF-Token": token },
    data: { title: "Polyglot" },
  });
  const { id } = (await item.json()) as { id: string };
  const fs = await import("node:fs");
  const polyglot = Buffer.concat([
    fs.readFileSync(PHOTO),
    Buffer.from("PK\x03\x04"),
    Buffer.alloc(200),
  ]);
  const r = await page.request.post(`/api/v1/me/portfolio/${id}/images`, {
    headers: { ...headers, "X-CSRF-Token": token },
    multipart: { file: { name: "photo.jpg", mimeType: "image/jpeg", buffer: polyglot } },
  });
  expect(r.status()).toBe(422);
  const body = (await r.json()) as { error: { fields: { file: string } } };
  expect(body.error.fields.file).toMatch(/extra data/);
});
