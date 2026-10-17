/**
 * Frame rate with the 3D scene running (spec §13.11, §13.12: steady 60 fps). Measures
 * requestAnimationFrame intervals for 3 s while the live constellation renders.
 */
import { expect, test } from "./test";

test("homepage holds 60 fps with the 3D scene running @perf", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect
    .poll(() => page.locator("[data-hero-mode]").getAttribute("data-hero-mode"), {
      timeout: 20_000,
    })
    .toBe("live");
  await page.waitForTimeout(1500); // let the PerformanceMonitor settle
  const intervals = await page.evaluate(
    () =>
      new Promise<number[]>((resolve) => {
        const times: number[] = [];
        const start = performance.now();
        const tick = (t: number) => {
          times.push(t);
          if (t - start < 3000) requestAnimationFrame(tick);
          else resolve(times.slice(1).map((v, i) => v - (times[i] ?? v)));
        };
        requestAnimationFrame(tick);
      }),
  );
  const fps = (intervals.length / intervals.reduce((a, b) => a + b, 0)) * 1000;
  const sorted = [...intervals].sort((a, b) => a - b);
  const p95 = sorted[Math.floor(sorted.length * 0.95)] ?? 0;
  console.log(`hero fps ${fps.toFixed(1)}, p95 frame ${p95.toFixed(1)} ms`);
  expect(fps).toBeGreaterThanOrEqual(58);
  expect(await page.locator("[data-hero-mode]").getAttribute("data-hero-mode")).toBe("live");
});
