/**
 * When the live 3D hero may run (spec §13.12 fallbacks): never with reduced motion, without
 * WebGL, in data-saver mode or on devices with fewer than 4 logical CPU cores. In those cases
 * only the poster shows and no WebGL context is ever created.
 */
export type HeroFallbackReason = "reduced-motion" | "no-webgl" | "save-data" | "low-cores" | null;

interface NavigatorLike {
  hardwareConcurrency?: number;
  connection?: { saveData?: boolean };
}

export function webglAvailable(doc: Document = document): boolean {
  try {
    const canvas = doc.createElement("canvas");
    const ctx = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    if (!ctx) return false;
    // Free the probe context straight away.
    ctx.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

export function heroFallbackReason(
  reducedMotion: boolean,
  nav: NavigatorLike = navigator,
  hasWebgl: () => boolean = webglAvailable,
): HeroFallbackReason {
  if (reducedMotion) return "reduced-motion";
  if (nav.connection?.saveData === true) return "save-data";
  if (typeof nav.hardwareConcurrency === "number" && nav.hardwareConcurrency < 4)
    return "low-cores";
  if (!hasWebgl()) return "no-webgl";
  return null;
}

/** requestIdleCallback with a timeout fallback (Safari has none). */
export function whenIdle(cb: () => void, timeout = 1500): () => void {
  const w: {
    requestIdleCallback?: typeof window.requestIdleCallback;
    cancelIdleCallback?: typeof window.cancelIdleCallback;
  } = window;
  if (w.requestIdleCallback && w.cancelIdleCallback) {
    const id = window.requestIdleCallback(cb, { timeout });
    return () => {
      window.cancelIdleCallback(id);
    };
  }
  const id = window.setTimeout(cb, 200);
  return () => {
    window.clearTimeout(id);
  };
}
