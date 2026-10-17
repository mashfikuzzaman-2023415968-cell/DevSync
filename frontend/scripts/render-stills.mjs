/**
 * npm run render:stills (spec §13.13): renders the constellation stills in light and dark at
 * 1x and 2x into src/assets/stills/*.webp and writes stills-manifest.json with a hash of the
 * scene files and tokens. Run inside the pinned Playwright image (make stills), so output is
 * reproducible; the gate fails when the manifest hash no longer matches.
 */
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import { createServer } from "vite";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const out = resolve(root, "src/assets/stills");
export const HASHED = [
  "src/components/three/TalentConstellation.tsx",
  "src/components/three/model.ts",
  "src/design/tokens.ts",
];

export function sceneHash() {
  const h = createHash("sha256");
  for (const f of HASHED) h.update(readFileSync(resolve(root, f)));
  return h.digest("hex");
}

const NAMES = ["hero-poster", "team"];
const THEMES = ["light", "dark"];
const SCALES = [1, 2];

async function main() {
  mkdirSync(out, { recursive: true });
  const server = await createServer({
    root,
    server: { port: 5174, host: "127.0.0.1", strictPort: true },
    logLevel: "error",
  });
  await server.listen();
  const browser = await chromium.launch({
    args: [
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--enable-unsafe-swiftshader",
      "--ignore-gpu-blocklist",
    ],
  });
  const files = [];
  try {
    for (const name of NAMES) {
      for (const theme of THEMES) {
        for (const scale of SCALES) {
          const page = await browser.newPage({ deviceScaleFactor: 1 });
          await page.goto(
            `http://127.0.0.1:5174/__stills?name=${name}&theme=${theme}&scale=${String(scale)}`,
          );
          await page.waitForFunction(() => window.__stillReady === true, null, { timeout: 60_000 });
          const dataUrl = await page.evaluate(() => {
            const canvas = document.querySelector("[data-still] canvas");
            return canvas instanceof HTMLCanvasElement ? canvas.toDataURL("image/webp", 0.86) : "";
          });
          if (!dataUrl.startsWith("data:image/webp"))
            throw new Error(`no WebP for ${name}/${theme}/${String(scale)}`);
          const file = `${name}-${theme}@${String(scale)}x.webp`;
          writeFileSync(resolve(out, file), Buffer.from(dataUrl.split(",")[1], "base64"));
          files.push(file);
          await page.close();
        }
      }
    }
    // Social preview image (spec §13.11): rendered from the light team still, saved as PNG.
    const page = await browser.newPage({
      viewport: { width: 1200, height: 630 },
      colorScheme: "light",
    });
    await page.goto("http://127.0.0.1:5174/__stills?name=social");
    await page.waitForFunction(() => {
      const img = document.querySelector("[data-social] img");
      return img instanceof HTMLImageElement && img.complete && img.naturalWidth > 0;
    });
    await page.evaluate(() => document.fonts.ready);
    await page
      .locator("[data-social]")
      .screenshot({ path: resolve(root, "public/social-preview.png") });
    await page.close();
  } finally {
    await browser.close();
    await server.close();
  }
  const manifest = { hash: sceneHash(), hashed: HASHED, files: files.sort() };
  writeFileSync(resolve(out, "stills-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`rendered ${String(files.length)} stills, hash ${manifest.hash.slice(0, 12)}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}
