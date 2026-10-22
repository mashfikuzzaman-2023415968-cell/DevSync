/**
 * When the live 3D hero may run (spec §13.12 fallbacks): never with reduced motion, without
 * WebGL, in data-saver mode, on devices with fewer than 4 logical CPU cores, or when WebGL would
 * render in software (no usable GPU — a VM or a laptop with its GPU blocked). Compiling the
 * scene's shaders in software can freeze the page for seconds (D54), so those visitors get the
 * poster too. In every fallback only the poster shows and no WebGL context is kept.
 */
export type HeroFallbackReason =
  "reduced-motion" | "no-webgl" | "software-webgl" | "save-data" | "low-cores" | null;

interface NavigatorLike {
  hardwareConcurrency?: number;
  connection?: { saveData?: boolean };
}

/** Software rasterisers browsers fall back to without a usable GPU. */
const SOFTWARE_RENDERER = /swiftshader|llvmpipe|softpipe|lavapipe|software|basic render/i;

type Probe = WebGLRenderingContext | WebGL2RenderingContext;

function probe(doc: Document, attributes?: WebGLContextAttributes): Probe | null {
  const canvas = doc.createElement("canvas");
  return canvas.getContext("webgl2", attributes) ?? canvas.getContext("webgl", attributes);
}

function release(ctx: Probe): void {
  ctx.getExtension("WEBGL_lose_context")?.loseContext();
}

export function webglAvailable(doc: Document = document): boolean {
  try {
    const ctx = probe(doc);
    if (!ctx) return false;
    // Free the probe context straight away.
    release(ctx);
    return true;
  } catch {
    return false;
  }
}

/** True when WebGL exists but would run without a GPU: the browser reports a major performance
 * caveat, or the renderer is a known software rasteriser (Chrome's SwiftShader, Mesa llvmpipe). */
export function webglIsSoftware(doc: Document = document): boolean {
  try {
    const strict = probe(doc, { failIfMajorPerformanceCaveat: true });
    if (!strict) return true;
    const info = strict.getExtension("WEBGL_debug_renderer_info");
    const renderer = info ? String(strict.getParameter(info.UNMASKED_RENDERER_WEBGL)) : "";
    release(strict);
    return SOFTWARE_RENDERER.test(renderer);
  } catch {
    return true;
  }
}

export function heroFallbackReason(
  reducedMotion: boolean,
  nav: NavigatorLike = navigator,
  hasWebgl: () => boolean = webglAvailable,
  isSoftware: () => boolean = webglIsSoftware,
): HeroFallbackReason {
  if (reducedMotion) return "reduced-motion";
  if (nav.connection?.saveData === true) return "save-data";
  if (typeof nav.hardwareConcurrency === "number" && nav.hardwareConcurrency < 4)
    return "low-cores";
  if (!hasWebgl()) return "no-webgl";
  if (isSoftware()) return "software-webgl";
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
