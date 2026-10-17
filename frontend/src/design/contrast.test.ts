/**
 * Every token pair used for text must meet WCAG 2.1 AA (4.5:1) in both themes
 * (spec §13.1), and tokens.css must match tokens.ts exactly.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { colors, cssVarName, type ColorTokens, type ThemeName } from "./tokens";

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * (r ?? 0) + 0.7152 * (g ?? 0) + 0.0722 * (b ?? 0);
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

type Key = Exclude<keyof ColorTokens, "chart">;
const TEXT_PAIRS: Array<[Key, Key]> = [
  ["text", "bg"],
  ["text", "surface"],
  ["text", "surface2"],
  ["textMuted", "bg"],
  ["textMuted", "surface"],
  ["textMuted", "surface2"],
  ["textSubtle", "surface"], // D10: subtle only on surface
  ["primary", "surface"],
  ["primary", "bg"],
  ["primary", "primarySoft"],
  ["onPrimary", "primary"],
  ["onPrimary", "primaryHover"],
  ["accent", "surface"],
  ["newcomer", "newcomerBg"],
  ["success", "successBg"],
  ["warning", "warningBg"],
  ["danger", "dangerBg"],
  ["info", "infoBg"],
  ["danger", "surface"],
  ["success", "surface"],
  ["onDanger", "danger"],
  ["warning", "surface"],
  ["info", "surface"],
  ["newcomer", "surface"],
  ["primary", "surface2"],
  ["textMuted", "primarySoft"],
];

describe.each<ThemeName>(["light", "dark"])("%s theme", (theme) => {
  it.each(TEXT_PAIRS)("%s on %s meets AA", (fg, bg) => {
    expect(contrast(colors[theme][fg], colors[theme][bg])).toBeGreaterThanOrEqual(4.5);
  });
});

describe("contrast()", () => {
  it("computes the known extremes", () => {
    expect(contrast("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#777777")).toBeCloseTo(1, 5);
  });

  it("documents why text-subtle is not used on bg (D10)", () => {
    expect(contrast(colors.light.textSubtle, colors.light.bg)).toBeLessThan(4.5);
  });
});

describe("tokens.css mirrors tokens.ts", () => {
  const css = readFileSync(resolve(__dirname, "tokens.css"), "utf8").toLowerCase();
  const [lightBlock, darkBlock] = [
    css.slice(css.indexOf(":root {"), css.indexOf("@media")),
    css.slice(css.indexOf(':root[data-theme="dark"]')),
  ];

  it.each<[ThemeName, string]>([
    ["light", lightBlock],
    ["dark", darkBlock],
  ])("%s values match", (theme, block) => {
    for (const [name, value] of Object.entries(colors[theme])) {
      if (name === "chart") {
        (value as readonly string[]).forEach((c, i) => {
          expect(block).toContain(`--chart-${i + 1}: ${c.toLowerCase()};`);
        });
      } else {
        expect(block).toContain(`${cssVarName(name)}: ${(value as string).toLowerCase()};`);
      }
    }
  });
});
