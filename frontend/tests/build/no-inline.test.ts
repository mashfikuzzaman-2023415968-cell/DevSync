/**
 * The production build must be compatible with the strict CSP (spec §14.3):
 * no inline scripts or styles, no inline event handlers, no external URLs,
 * and no source maps referenced. Runs after `npm run build` (skipped otherwise).
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const dist = resolve(__dirname, "../../dist");
const indexPath = resolve(dist, "index.html");
const built = existsSync(indexPath);

describe.skipIf(!built)("production build", () => {
  const html = built ? readFileSync(indexPath, "utf8") : "";

  it("has no inline <script> bodies", () => {
    const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)];
    expect(scripts.length).toBeGreaterThan(0);
    for (const [, attrs, body] of scripts) {
      expect(attrs).toMatch(/\bsrc=/);
      expect((body ?? "").trim()).toBe("");
    }
  });

  it("has no <style> elements or style= attributes", () => {
    expect(html).not.toMatch(/<style\b/i);
    expect(html).not.toMatch(/\sstyle=/i);
  });

  it("has no inline event handlers or javascript: URLs", () => {
    expect(html).not.toMatch(/\son[a-z]+=/i);
    expect(html).not.toMatch(/javascript:/i);
  });

  it("loads nothing from other origins", () => {
    expect(html).not.toMatch(/(src|href)=["']https?:\/\//i);
  });

  it("does not reference source maps", () => {
    const assets = resolve(dist, "assets");
    for (const file of readdirSync(assets)) {
      if (file.endsWith(".js") || file.endsWith(".css")) {
        expect(readFileSync(resolve(assets, file), "utf8")).not.toMatch(/sourceMappingURL/);
      }
    }
  });
});
