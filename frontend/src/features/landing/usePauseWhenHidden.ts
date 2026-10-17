import { useEffect, useState, type RefObject } from "react";

/** True while the element is on screen and the tab is visible (spec §13.11: animations pause
 * off screen or in a hidden tab to save CPU and battery). */
export function useActiveWhenVisible(ref: RefObject<Element>, rootMargin = "0px"): boolean {
  const [onScreen, setOnScreen] = useState(true);
  const [tabVisible, setTabVisible] = useState(
    () => typeof document === "undefined" || !document.hidden,
  );
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return undefined;
    const io = new IntersectionObserver(
      ([entry]) => {
        setOnScreen(entry?.isIntersecting ?? true);
      },
      { rootMargin },
    );
    io.observe(el);
    return () => {
      io.disconnect();
    };
  }, [ref, rootMargin]);
  useEffect(() => {
    const onVis = () => {
      setTabVisible(!document.hidden);
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);
  return onScreen && tabVisible;
}
