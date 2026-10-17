/**
 * The hero poster drawn into a 2D canvas (spec §13.12 "poster first"). A canvas is never a
 * Largest Contentful Paint candidate, so the headline stays the LCP element (§13.12) while the
 * pre-rendered still appears straight away. Redraws on theme change and resize.
 */
import { useEffect, useRef } from "react";
import { NodeArt } from "@/components/brand/NodeArt";
import { still } from "@/components/brand/stills";
import type { ThemeName } from "@/design/tokens";
import { cn } from "@/lib/cn";

export function PosterCanvas({ theme, className }: { theme: ThemeName; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const source = still("hero-poster", theme);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !source) return undefined;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const img = new Image();
    img.decoding = "async";
    img.src = dpr > 1 ? (source.srcSet.split(", ")[1]?.split(" ")[0] ?? source.src) : source.src;
    let cancelled = false;
    const draw = () => {
      if (cancelled || !img.complete || !img.naturalWidth) return;
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const scale = Math.min(canvas.width / img.naturalWidth, canvas.height / img.naturalHeight);
      const w = img.naturalWidth * scale;
      const h = img.naturalHeight * scale;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
      canvas.dataset.drawn = "true";
    };
    img.onload = draw;
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(draw);
    observer?.observe(canvas);
    return () => {
      cancelled = true;
      observer?.disconnect();
    };
  }, [source]);
  if (!source) return <NodeArt className={cn("size-full", className)} />;
  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      data-hero-poster=""
      className={cn("size-full", className)}
    />
  );
}
