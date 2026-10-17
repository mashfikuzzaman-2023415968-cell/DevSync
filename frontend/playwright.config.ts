/**
 * Playwright (spec §16.1): Chromium on every phase; Firefox, WebKit and a mobile
 * viewport at the demo phases. Runs against Nginx over HTTPS (self-signed in dev/CI).
 * Chromium renders WebGL with SwiftShader inside the container (the 3D hero tests).
 * Visual baselines live in e2e/__screenshots__ and are made in the pinned Playwright image.
 */
import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "https://localhost";
const webgl = [
  "--use-gl=angle",
  "--use-angle=swiftshader",
  "--enable-unsafe-swiftshader",
  "--ignore-gpu-blocklist",
];

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  // One worker: every test resets the shared per-IP rate limits (e2e/test.ts), so tests must
  // not overlap.
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  snapshotPathTemplate: "{testDir}/__screenshots__/{testFilePath}/{arg}{ext}",
  expect: {
    toHaveScreenshot: { maxDiffPixelRatio: 0.001, threshold: 0.2 },
  },
  use: {
    baseURL,
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], launchOptions: { args: webgl } } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
    { name: "mobile", use: { ...devices["iPhone 14"] } },
  ],
});
