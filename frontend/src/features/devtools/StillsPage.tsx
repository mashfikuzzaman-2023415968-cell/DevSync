/**
 * Development-only still renderer (spec §13.13): `/__stills?name=hero-poster&theme=dark&scale=2`
 * draws the constellation at a fixed moment so `npm run render:stills` can save it as WebP.
 * Not part of production builds.
 */
import { useSearchParams } from "react-router";
import TalentConstellation from "@/components/three/TalentConstellation";
import { STILL_SIZE, type StillName } from "@/components/brand/stills";
import type { ThemeName } from "@/design/tokens";

declare global {
  interface Window {
    __stillReady?: boolean;
  }
}

export default function StillsPage() {
  const [params] = useSearchParams();
  const name: StillName = params.get("name") === "team" ? "team" : "hero-poster";
  const theme: ThemeName = params.get("theme") === "dark" ? "dark" : "light";
  const scale = params.get("scale") === "2" ? 2 : 1;
  const size = STILL_SIZE[name];
  return (
    <main className="p-0">
      <h1 className="sr-only">Still {name}</h1>
      <div data-still={name} style={{ width: size.width, height: size.height }}>
        <TalentConstellation
          theme={theme}
          active
          snap={name === "team" ? 1 : 0}
          angle={name === "team" ? 0.6 : 0.35}
          dpr={scale}
          chipText=""
          onReady={() => {
            // Two more frames so the environment map and colours have settled.
            requestAnimationFrame(() =>
              requestAnimationFrame(() => {
                window.__stillReady = true;
              }),
            );
          }}
        />
      </div>
    </main>
  );
}
