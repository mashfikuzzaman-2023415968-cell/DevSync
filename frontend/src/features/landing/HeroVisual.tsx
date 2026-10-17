/**
 * Hero visual (spec §13.12 performance guardrails): the poster shows immediately; the 3D chunk
 * loads after first paint when the hero is visible and the browser is idle, then the live
 * canvas cross-fades over the poster (400 ms). With reduced motion, no WebGL, data saver or
 * < 4 cores only the poster shows and no WebGL context is created. The canvas is decorative;
 * a visually hidden sentence describes the idea.
 */
import { lazy, Suspense, useEffect, useState } from "react";
import { useMediaQuery, usePreferences } from "@/design/preferences";
import { cn } from "@/lib/cn";
import { heroFallbackReason, whenIdle } from "./heroSupport";
import { PosterCanvas } from "./PosterCanvas";

const TalentConstellation = lazy(() => import("@/components/three/TalentConstellation"));

export const HERO_DESCRIPTION =
  "Illustration: many developers drawn as glowing points. As you scroll, four of them move together into a balanced team, one of them a newcomer.";

export function HeroVisual({ active }: { active: boolean }) {
  const { resolvedTheme, reducedMotion } = usePreferences();
  const compact = !useMediaQuery("(min-width: 1024px)");
  const [reason] = useState(() => heroFallbackReason(reducedMotion));
  const [load, setLoad] = useState(false);
  const [ready, setReady] = useState(false);
  const [lost, setLost] = useState(false);
  const live = !reducedMotion && reason === null && !lost;

  useEffect(() => {
    if (!live || load || !active) return undefined;
    return whenIdle(() => {
      setLoad(true);
    });
  }, [live, load, active]);

  return (
    <div
      className="relative mx-auto aspect-[8/7] w-full max-w-[560px] lg:max-w-none"
      data-hero-mode={live ? (ready ? "live" : "poster") : "poster-only"}
      data-fallback={reason ?? (lost ? "context-lost" : undefined)}
    >
      <p className="sr-only">{HERO_DESCRIPTION}</p>
      <PosterCanvas
        theme={resolvedTheme}
        className={cn(
          "absolute inset-0 transition-opacity duration-crossfade",
          ready && live && "opacity-0",
        )}
      />
      {live && load ? (
        <div
          className={cn(
            "absolute inset-0 transition-opacity duration-crossfade",
            ready ? "opacity-100" : "opacity-0",
          )}
        >
          <Suspense fallback={null}>
            <TalentConstellation
              theme={resolvedTheme}
              active={active}
              compact={compact}
              onReady={() => {
                setReady(true);
              }}
              onContextLost={() => {
                setLost(true);
              }}
            />
          </Suspense>
        </div>
      ) : null}
    </div>
  );
}
