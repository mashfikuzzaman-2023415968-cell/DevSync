/**
 * Still renders of the 3D constellation (spec §13.13), produced by `npm run render:stills`
 * into src/assets/stills/: `<name>-<theme>@<1|2>x.webp` for name ∈ {hero-poster, team}.
 * Glob import so the app still builds before the first render (callers fall back to SVG).
 */
import type { ThemeName } from "@/design/tokens";

const files = import.meta.glob<string>("../../assets/stills/*.webp", {
  eager: true,
  query: "?url",
  import: "default",
});

export type StillName = "hero-poster" | "team";

export interface StillSource {
  src: string;
  srcSet: string;
}

export function still(name: StillName, theme: ThemeName): StillSource | null {
  const one = files[`../../assets/stills/${name}-${theme}@1x.webp`];
  const two = files[`../../assets/stills/${name}-${theme}@2x.webp`];
  if (!one) return null;
  return { src: one, srcSet: two ? `${one} 1x, ${two} 2x` : `${one} 1x` };
}

/** Pixel size of the 1x renders (explicit width/height avoid layout shift, spec §13.7). */
export const STILL_SIZE: Record<StillName, { width: number; height: number }> = {
  "hero-poster": { width: 640, height: 560 },
  team: { width: 480, height: 360 },
};
