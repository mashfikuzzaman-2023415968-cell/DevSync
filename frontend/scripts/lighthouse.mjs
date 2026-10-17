/**
 * Homepage Lighthouse check (spec §13.11 performance targets, §17 Phase 2 gate):
 * desktop Performance ≥ 90, mobile ≥ 80; Accessibility ≥ 95, Best practices ≥ 95, SEO ≥ 90 on
 * both; desktop LCP < 2.0 s; CLS < 0.05 on both. Runs in the pinned Playwright image with its
 * Chromium against the HTTPS stack (LH_URL). Writes a summary to LH_OUT.
 */
import { writeFileSync } from "node:fs";
import { chromium } from "@playwright/test";
import * as chromeLauncher from "chrome-launcher";
import lighthouse from "lighthouse";
import desktopConfig from "lighthouse/core/config/desktop-config.js";

const url = process.env.LH_URL ?? "https://localhost:8443/";
const out = process.env.LH_OUT ?? "lighthouse-summary.json";

const TARGETS = {
  desktop: {
    performance: 90,
    accessibility: 95,
    "best-practices": 95,
    seo: 90,
    lcpMs: 2000,
    cls: 0.05,
  },
  mobile: {
    performance: 80,
    accessibility: 95,
    "best-practices": 95,
    seo: 90,
    lcpMs: null,
    cls: 0.05,
  },
};

async function audit(profile) {
  const chrome = await chromeLauncher.launch({
    chromePath: chromium.executablePath(),
    chromeFlags: [
      "--headless=new",
      "--no-sandbox",
      "--ignore-certificate-errors",
      "--disable-dev-shm-usage",
    ],
  });
  try {
    const flags = { port: chrome.port, output: "json", logLevel: "error" };
    const result = await lighthouse(url, flags, profile === "desktop" ? desktopConfig : undefined);
    const lhr = result.lhr;
    const scores = Object.fromEntries(
      ["performance", "accessibility", "best-practices", "seo"].map((c) => [
        c,
        Math.round((lhr.categories[c].score ?? 0) * 100),
      ]),
    );
    const lcp = lhr.audits["largest-contentful-paint"].numericValue;
    const cls = lhr.audits["cumulative-layout-shift"].numericValue;
    const failing = Object.values(lhr.audits)
      .filter((a) => a.score !== null && a.score < 0.9 && a.scoreDisplayMode === "binary")
      .map((a) => a.id);
    return { profile, scores, lcpMs: Math.round(lcp), cls: Number(cls.toFixed(3)), failing };
  } finally {
    await chrome.kill();
  }
}

const results = [];
const problems = [];
for (const profile of ["desktop", "mobile"]) {
  const r = await audit(profile);
  results.push(r);
  const t = TARGETS[profile];
  for (const c of ["performance", "accessibility", "best-practices", "seo"]) {
    if (r.scores[c] < t[c])
      problems.push(`${profile} ${c} ${String(r.scores[c])} < ${String(t[c])}`);
  }
  if (t.lcpMs !== null && r.lcpMs >= t.lcpMs)
    problems.push(`${profile} LCP ${String(r.lcpMs)} ms ≥ ${String(t.lcpMs)} ms`);
  if (r.cls >= t.cls) problems.push(`${profile} CLS ${String(r.cls)} ≥ ${String(t.cls)}`);
}
writeFileSync(out, `${JSON.stringify({ url, results, problems }, null, 2)}\n`);
for (const r of results) {
  console.log(
    `${r.profile}: perf ${String(r.scores.performance)} a11y ${String(r.scores.accessibility)} bp ${String(r.scores["best-practices"])} seo ${String(r.scores.seo)} LCP ${String(r.lcpMs)}ms CLS ${String(r.cls)}${r.failing.length ? ` failing: ${r.failing.join(",")}` : ""}`,
  );
}
if (problems.length) {
  console.log(`LIGHTHOUSE FAIL: ${problems.join("; ")}`);
  process.exit(1);
}
console.log("LIGHTHOUSE PASS");
