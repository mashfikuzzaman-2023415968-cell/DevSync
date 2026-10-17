/**
 * Development-only still renderer (spec §13.13): `/__stills?name=hero-poster&theme=dark&scale=2`
 * draws the constellation at a fixed moment so `npm run render:stills` can save it as WebP.
 * Not part of production builds.
 */
import { useSearchParams } from "react-router";
import { Wordmark } from "@/components/brand/Logo";
import { Still } from "@/components/brand/Still";
import TalentConstellation from "@/components/three/TalentConstellation";
import { STILL_SIZE, type StillName } from "@/components/brand/stills";
import type { ThemeName } from "@/design/tokens";

declare global {
  interface Window {
    __stillReady?: boolean;
  }
}

/** 1200×630 social preview: brand background, headline and the team still. */
function SocialPreview() {
  return (
    <div
      data-social=""
      className="flex items-center gap-10 bg-gradient-to-br from-primary-soft via-bg to-bg px-16"
      style={{ width: 1200, height: 630 }}
    >
      <div className="flex-1">
        <Wordmark className="text-h3" />
        <p className="mt-8 text-[56px] font-semibold leading-[1.1] tracking-tight text-text">
          Plan the project.
          <br />
          Hire a fair team.
        </p>
        <p className="mt-6 text-[24px] text-text-muted">
          Freelance software teams, newcomers included.
        </p>
      </div>
      <Still name="team" eager className="w-[460px]" />
    </div>
  );
}

export default function StillsPage() {
  const [params] = useSearchParams();
  if (params.get("name") === "social") return <SocialPreview />;
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
