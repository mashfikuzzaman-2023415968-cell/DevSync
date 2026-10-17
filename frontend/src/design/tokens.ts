/**
 * Design tokens (spec §13.1) — the single source of truth for colours.
 * `tokens.css` defines the same values as CSS variables; `contrast.test.ts`
 * keeps the two in sync and checks every text/background pair for WCAG AA.
 * The homepage 3D scene (Phase 2) reads these values too (§13.13).
 */

export type ThemeName = "light" | "dark";

export interface ColorTokens {
  bg: string;
  surface: string;
  surface2: string;
  border: string;
  text: string;
  textMuted: string;
  textSubtle: string;
  primary: string;
  primaryHover: string;
  primarySoft: string;
  onPrimary: string;
  accent: string;
  newcomer: string;
  newcomerBg: string;
  success: string;
  successBg: string;
  warning: string;
  warningBg: string;
  danger: string;
  dangerBg: string;
  onDanger: string;
  info: string;
  infoBg: string;
  chart: readonly [string, string, string, string, string, string];
}

export const colors: Record<ThemeName, ColorTokens> = {
  light: {
    bg: "#F7F8FA",
    surface: "#FFFFFF",
    surface2: "#F1F5F9",
    border: "#E2E8F0",
    text: "#0F172A",
    textMuted: "#475569",
    textSubtle: "#64748B",
    primary: "#0F766E",
    primaryHover: "#115E59",
    primarySoft: "#E6F4F2",
    onPrimary: "#FFFFFF",
    accent: "#4F46E5",
    newcomer: "#B45309",
    newcomerBg: "#FEF3C7",
    success: "#047857",
    successBg: "#ECFDF5",
    warning: "#B45309",
    warningBg: "#FFFBEB",
    danger: "#BE123C",
    dangerBg: "#FFF1F2",
    onDanger: "#FFFFFF",
    info: "#0369A1",
    infoBg: "#F0F9FF",
    chart: ["#0F766E", "#4F46E5", "#D97706", "#BE123C", "#0369A1", "#64748B"],
  },
  dark: {
    bg: "#0B1220",
    surface: "#111827",
    surface2: "#1E293B",
    border: "#273449",
    text: "#E5E7EB",
    textMuted: "#A1A1AA",
    textSubtle: "#94A3B8",
    primary: "#2DD4BF",
    primaryHover: "#5EEAD4",
    primarySoft: "#0F2E2B",
    onPrimary: "#042F2E",
    accent: "#818CF8",
    newcomer: "#FCD34D",
    newcomerBg: "#3A2A0A",
    success: "#34D399",
    successBg: "#062A1F",
    warning: "#FBBF24",
    warningBg: "#33240A",
    danger: "#FB7185",
    dangerBg: "#3B0A16",
    onDanger: "#2A0611",
    info: "#38BDF8",
    infoBg: "#082236",
    chart: ["#2DD4BF", "#818CF8", "#FBBF24", "#FB7185", "#38BDF8", "#94A3B8"],
  },
};

/** CSS variable name for each token (kebab case, e.g. `textMuted` → `--text-muted`). */
export function cssVarName(token: string): string {
  return `--${token.replace(/([a-z0-9])([A-Z0-9])/g, "$1-$2").toLowerCase()}`;
}
