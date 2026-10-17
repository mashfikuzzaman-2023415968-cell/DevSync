import { usePreferences } from "@/design/preferences";
import { cn } from "@/lib/cn";
import { NodeArt } from "./NodeArt";
import { STILL_SIZE, still, type StillName } from "./stills";

/** A decorative still of the constellation in the current theme (SVG motif until rendered). */
export function Still({
  name,
  className,
  eager = false,
}: {
  name: StillName;
  className?: string;
  eager?: boolean;
}) {
  const { resolvedTheme } = usePreferences();
  const source = still(name, resolvedTheme);
  if (!source) return <NodeArt className={className} />;
  const size = STILL_SIZE[name];
  return (
    <img
      src={source.src}
      srcSet={source.srcSet}
      width={size.width}
      height={size.height}
      alt=""
      aria-hidden="true"
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      className={cn("h-auto max-w-full select-none", className)}
    />
  );
}
