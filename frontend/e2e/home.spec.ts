/**
 * Homepage and 3D hero (spec §17 Phase 2 tests, §13.11–13.12).
 */
import { chromium, type Page } from "@playwright/test";
import { expect, test } from "./test";
import { apiSignIn } from "./fixtures";

const HEADLINE = "Plan the project. Hire a fair team. Watch the work. Learn from it.";
const SCENE_CHUNK = /TalentConstellation-[\w-]+\.js$/;

async function heroMode(page: Page) {
  return page.locator("[data-hero-mode]").getAttribute("data-hero-mode");
}

/** Below this width the homepage header collapses into the "Open menu" sheet (Tailwind lg). */
const PHONE_MAX = 1024;

/** Phones load the 3D scene on the first scroll, touch or key press (D26); desktops load it on
 * their own. A key press wakes it without clicking anything. */
async function wakeHero(page: Page) {
  await page.keyboard.press("Shift");
}

/** Expect the live 3D scene. It needs a real GPU: the `chromium-gpu` project (gate step 16, with
 * /dev/dri) must reach it. Everywhere else in the test container WebGL is software (Chromium's
 * SwiftShader, WebKit) or missing (Firefox), so the page must fall back to its poster — drawn,
 * with the app's own reason — and the live-scene part is skipped with that reason (D53, D54).
 * WebKit hides its renderer name, so it may still go live; that is accepted too. */
async function expectLiveScene(page: Page) {
  const outcome = await liveOrPoster(page);
  if (outcome.live) return;
  test.skip(
    true,
    `${outcome.project}: no hardware WebGL in the test container (mode ${outcome.mode}, fallback ${outcome.fallback}); poster fallback verified, live scene checked on chromium-gpu`,
  );
}

/** The scene goes live (required on chromium-gpu), or the poster fallback is verified. */
async function liveOrPoster(page: Page) {
  await wakeHero(page);
  const project = test.info().project.name;
  if (project === "chromium-gpu") {
    await expect.poll(() => heroMode(page), { timeout: 20_000 }).toBe("live");
    return { live: true, project, mode: "live", fallback: "none" };
  }
  const live = await expect
    .poll(() => heroMode(page), { timeout: 8_000 })
    .toBe("live")
    .then(() => true)
    .catch(() => false);
  if (live) return { live: true, project, mode: "live", fallback: "none" };
  const mode = String(await heroMode(page));
  const fallback = (await page.locator("[data-hero-mode]").getAttribute("data-fallback")) ?? "none";
  await expect(page.locator("canvas[data-hero-poster]")).toHaveAttribute("data-drawn", "true");
  expect(["poster", "poster-only"]).toContain(mode);
  if (project === "chromium") expect(fallback).toBe("software-webgl");
  return { live: false, project, mode, fallback };
}

async function scrollBy(page: Page, dy: number, isMobile: boolean) {
  if (isMobile) {
    await page.evaluate((y) => {
      window.scrollBy(0, y);
    }, dy); // mobile WebKit has no wheel events
  } else {
    await page.mouse.wheel(0, dy);
  }
}

test("a fresh visit to / shows the homepage, not login @e2e", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1, name: HEADLINE })).toBeVisible();
  await expect(page).toHaveTitle("DevSync · Plan, hire a fair team, deliver");
});

test("navbar, hero, call-to-action and footer links reach the right pages @e2e", async ({
  page,
}) => {
  // These checks are about where links go, not the 3D hero (covered below). In the test
  // container WebKit renders WebGL in software and its shader compile can block the page for
  // seconds, swallowing clicks; reduced motion shows the poster instead (D53).
  await page.emulateMedia({ reducedMotion: "reduce" });
  const checks: [string, string, RegExp][] = [
    ["header", "Sign in", /\/login$/],
    ["header", "Get started", /\/register$/],
    ["header", "Browse projects", /\/projects$/],
    ["hero", "Hire a team", /\/register\?role=client$/],
    ["hero", "Find work", /\/register\?role=developer$/],
    ["footer", "Privacy", /\/privacy$/],
    ["footer", "Terms of use", /\/terms$/],
    ["footer", "Find work", /\/register\?role=developer$/],
  ];
  for (const [area, name, url] of checks) {
    await page.goto("/");
    const scope =
      area === "header"
        ? page.locator("header").first()
        : area === "hero"
          ? page.locator("section[aria-labelledby=hero-title]")
          : page.locator("footer");
    let link = scope.getByRole("link", { name, exact: true }).first();
    if (area === "header" && (page.viewportSize()?.width ?? 1280) < PHONE_MAX) {
      // Phones: the header links sit in the menu sheet.
      await page.getByRole("button", { name: "Open menu" }).click();
      link = page.getByRole("dialog").getByRole("link", { name, exact: true }).first();
    }
    await link.click();
    await expect(page, `${area} → ${name}`).toHaveURL(url);
  }
  await page.goto("/");
  const how = page.locator("header").first().getByRole("link", { name: "How it works" });
  if ((page.viewportSize()?.width ?? 1280) >= PHONE_MAX) {
    await how.click();
  } else {
    await page.getByRole("button", { name: "Open menu" }).click();
    await page.getByRole("dialog").getByRole("link", { name: "How it works" }).click();
  }
  await expect(page).toHaveURL(/#how-it-works$/);
});

test("Hire a team preselects Client and Find work preselects Developer @e2e", async ({ page }) => {
  // These checks are about where links go, not the 3D hero (covered below). In the test
  // container WebKit renders WebGL in software and its shader compile can block the page for
  // seconds, swallowing clicks; reduced motion shows the poster instead (D53).
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page
    .locator("section[aria-labelledby=hero-title]")
    .getByRole("link", { name: "Hire a team" })
    .click();
  await expect(page.getByRole("heading", { name: "Your details" })).toBeVisible();
  await expect(page.getByText("You’re signing up to hire a team.")).toBeVisible();
  await page.goto("/");
  await page
    .locator("section[aria-labelledby=hero-title]")
    .getByRole("link", { name: "Find work" })
    .click();
  await expect(page.getByText("You’re signing up to find work.")).toBeVisible();
});

test("signed-in users opening / land on their role home; logout returns to / @e2e", async ({
  page,
  baseURL,
}) => {
  await apiSignIn(page, baseURL ?? "", "CLIENT");
  await page.goto("/");
  await expect(page).toHaveURL(/\/client$/);
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1, name: HEADLINE })).toBeVisible();
});

test("poster shows first, the headline is the LCP element and the live scene follows @e2e @gpu", async ({
  page,
  isMobile,
}) => {
  await page.addInitScript(() => {
    (window as unknown as { __lcp: string[] }).__lcp = [];
    new PerformanceObserver((list) => {
      for (const e of list.getEntries() as (PerformanceEntry & { element?: Element | null })[]) {
        const el = e.element;
        const inHero = el?.closest("section[aria-labelledby=hero-title]") ? "@hero" : "";
        (window as unknown as { __lcp: string[] }).__lcp.push(
          el ? `${el.tagName}#${el.id}${inHero}` : "none",
        );
      }
    }).observe({ type: "largest-contentful-paint", buffered: true });
  });
  await page.goto("/");
  await expect(page.locator("canvas[data-hero-poster]")).toHaveAttribute("data-drawn", "true");
  // The heading becomes one plain text block once its words have appeared.
  await expect(page.locator("#hero-title")).toBeVisible();
  await expect(page.locator("#hero-title span")).toHaveCount(0);
  await expectLiveScene(page);
  // Interacting finalizes LCP.
  await page.mouse.click(5, 300);
  const lcp = await page.evaluate(() => (window as unknown as { __lcp: string[] }).__lcp);
  // Desktop: the headline. Phones: the hero's text either way (the lead paragraph's block can be
  // larger than the headline on a narrow screen) — never the canvas or an image.
  if (isMobile) expect(["H1#hero-title@hero", "P#@hero"]).toContain(lcp.at(-1));
  else expect(lcp.at(-1)).toBe("H1#hero-title@hero");
});

test("scrolling snaps the constellation into a team with the chip @e2e @gpu", async ({
  page,
  isMobile,
}) => {
  await page.goto("/");
  await expectLiveScene(page);
  const chip = page.locator("[data-hero-chip]");
  const opacity = async () => Number(await chip.evaluate((el) => getComputedStyle(el).opacity));
  await expect(chip).toHaveCSS("opacity", "0");
  await scrollBy(page, 650, isMobile);
  await expect.poll(opacity, { timeout: 10_000 }).toBeGreaterThan(0.9);
  await expect(chip).toHaveText("✓ Balanced team");
  // Scrolling back up releases the team.
  await scrollBy(page, -650, isMobile);
  await expect.poll(opacity, { timeout: 10_000 }).toBeLessThan(0.1);
});

test("the render loop stops when the hero is off screen @e2e @gpu", async ({ page }) => {
  await page.goto("/");
  await expectLiveScene(page);
  const frames = () =>
    page.evaluate(() => (window as unknown as { __dsHeroFrames?: number }).__dsHeroFrames ?? 0);
  const a = await frames();
  await page.waitForTimeout(500);
  expect(await frames()).toBeGreaterThan(a);
  await page.evaluate(() => {
    window.scrollTo(0, document.body.scrollHeight / 2);
  });
  // Wait until the render loop has actually paused (the frame count stops rising) rather than
  // assuming a fixed settle time, which is flaky on slower machines; then confirm it stays paused.
  await expect
    .poll(
      async () => {
        const before = await frames();
        await page.waitForTimeout(200);
        return (await frames()) - before;
      },
      { timeout: 10_000 },
    )
    .toBe(0);
  const b = await frames();
  await page.waitForTimeout(800);
  expect(await frames()).toBe(b);
});

async function countWebglContexts(page: Page) {
  await page.addInitScript(() => {
    // eslint-disable-next-line @typescript-eslint/unbound-method -- re-applied with the canvas as `this`
    const original = HTMLCanvasElement.prototype.getContext;
    (window as unknown as { __webgl: number }).__webgl = 0;
    HTMLCanvasElement.prototype.getContext = function (
      this: HTMLCanvasElement,
      type: string,
      ...rest: unknown[]
    ) {
      const ctx = (original as (...a: unknown[]) => unknown).call(this, type, ...rest);
      if (ctx && type.startsWith("webgl")) (window as unknown as { __webgl: number }).__webgl += 1;
      return ctx;
    } as typeof original;
  });
}

for (const [label, setup] of [
  ["reduced motion", (page: Page) => page.emulateMedia({ reducedMotion: "reduce" })],
  [
    "data saver",
    (page: Page) =>
      page.addInitScript(() => {
        Object.defineProperty(navigator, "connection", { value: { saveData: true } });
      }),
  ],
  [
    "fewer than 4 cores",
    (page: Page) =>
      page.addInitScript(() => {
        Object.defineProperty(navigator, "hardwareConcurrency", { value: 2 });
      }),
  ],
] as const) {
  test(`${label}: poster only, no WebGL context @e2e`, async ({ page }) => {
    await countWebglContexts(page);
    await setup(page);
    await page.goto("/");
    await expect(page.locator("[data-hero-mode]")).toHaveAttribute("data-hero-mode", "poster-only");
    await page.waitForTimeout(2500);
    expect(
      await page
        .locator("section[aria-labelledby=hero-title] canvas:not([data-hero-poster])")
        .count(),
    ).toBe(0);
    expect(await page.evaluate(() => (window as unknown as { __webgl: number }).__webgl)).toBe(0);
  });
}

test("WebGL disabled in the browser: poster only, no canvas @e2e", async ({ baseURL }) => {
  const browser = await chromium.launch({ args: ["--disable-webgl", "--disable-3d-apis"] });
  const page = await browser.newPage({ ignoreHTTPSErrors: true, baseURL: baseURL ?? "" });
  await page.goto("/");
  await expect(page.locator("[data-hero-mode]")).toHaveAttribute("data-hero-mode", "poster-only");
  await expect(page.locator("[data-hero-mode]")).toHaveAttribute("data-fallback", "no-webgl");
  await page.waitForTimeout(2000);
  expect(
    await page
      .locator("section[aria-labelledby=hero-title] canvas:not([data-hero-poster])")
      .count(),
  ).toBe(0);
  await browser.close();
});

test("reduced motion shows final states with no movement @e2e", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  // The headline is plain text straight away: no word-by-word reveal.
  await expect(page.locator("#hero-title")).toHaveText(HEADLINE, {
    useInnerText: false,
  });
  expect(await page.locator("#hero-title span").count()).toBe(0);
  await page.locator("#faq").scrollIntoViewIfNeeded();
  await expect(page.getByRole("heading", { name: "Questions people ask" })).toHaveCSS(
    "opacity",
    "1",
  );
  await expect(
    page.getByText("Based on published research from the University of Dhaka."),
  ).toBeVisible();
});

test("the 3D chunk is never requested off the homepage; nothing leaves the origin @e2e @gpu", async ({
  page,
  baseURL,
}) => {
  const origin = new URL(baseURL ?? "https://localhost").origin;
  const requested: string[] = [];
  page.on("request", (r) => requested.push(r.url()));
  for (const path of ["/login", "/register", "/projects", "/privacy"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
  }
  expect(requested.filter((u) => SCENE_CHUNK.test(u))).toEqual([]);
  requested.length = 0;
  await page.goto("/");
  const { live, fallback } = await liveOrPoster(page);
  // The chunk loads when the scene runs, and never when a fallback was decided up front (WebKit
  // may still be compiling in software: then neither is asserted).
  if (live) expect(requested.some((u) => SCENE_CHUNK.test(u))).toBe(true);
  else if (fallback !== "none") expect(requested.some((u) => SCENE_CHUNK.test(u))).toBe(false);
  expect(requested.filter((u) => u.startsWith("http") && new URL(u).origin !== origin)).toEqual([]);
});
