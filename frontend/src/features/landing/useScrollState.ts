import { useEffect, useRef, useState } from "react";

/** Scroll position helpers for the sticky navbar (spec §13.11 #1): solid after 24 px, hidden
 * while scrolling down fast, back on any scroll up. */
export function useScrollState() {
  const [state, setState] = useState({ scrolled: false, hidden: false, far: false });
  const last = useRef({ y: 0, t: 0 });
  const mounted = useRef(0);
  useEffect(() => {
    let frame = 0;
    mounted.current = performance.now();
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const y = window.scrollY;
        const t = performance.now();
        const dy = y - last.current.y;
        const speed = dy / Math.max(1, t - last.current.t); // px per ms
        last.current = { y, t };
        setState((s) => {
          // Only a person scrolling down fast hides the bar: not a restored scroll position,
          // an anchor jump or the first moment after the page opens.
          const jump = Math.abs(dy) > 400 || t - mounted.current < 600;
          const hidden = y > 120 && !jump && (dy > 0 ? speed > 0.6 || s.hidden : false);
          const next = { scrolled: y > 24, hidden, far: y > window.innerHeight * 2 };
          return next.scrolled === s.scrolled && next.hidden === s.hidden && next.far === s.far
            ? s
            : next;
        });
      });
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
    };
  }, []);
  return state;
}
