/**
 * robots.txt must not advertise the admin area (spec §14.17): it is hidden with 404s and
 * `X-Robots-Tag: noindex` from Nginx and the API instead of being named for crawlers.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const robots = readFileSync(resolve(__dirname, "../../public/robots.txt"), "utf8").toLowerCase();

describe("robots.txt", () => {
  it("never names the admin area", () => {
    expect(robots).not.toContain("admin");
  });

  it("still keeps crawlers out of the API and private areas", () => {
    expect(robots).toContain("disallow: /api");
    expect(robots).toContain("disallow: /settings");
  });
});
