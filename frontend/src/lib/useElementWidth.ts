/** Width of an element in CSS pixels, tracked with a ResizeObserver where available (0 until
 * measured, and in environments without ResizeObserver such as unit tests). Charts use it to
 * draw at their real size, so their 12 px labels stay 12 px at every viewport (§13.8 #6). */
import { useEffect, useRef, useState } from "react";

export function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      setWidth(Math.floor(entry?.contentRect.width ?? 0));
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, []);
  return [ref, width] as const;
}
