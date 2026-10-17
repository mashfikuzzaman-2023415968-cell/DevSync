import { animate, useInView } from "framer-motion";
import { useEffect, useRef, useState, type RefObject } from "react";
import { ease, timing } from "@/design/motion";
import { useReducedMotion } from "@/design/preferences";

/** Count up to `target` the first time the element scrolls into view (600 ms, spec §13.2);
 * later changes animate from the previous value. Reduced motion shows the final number. */
export function useCountUp<T extends Element>(target: number): [RefObject<T>, number] {
  const ref = useRef<T>(null);
  const inView = useInView(ref, { once: true, amount: 0.4 });
  const reduced = useReducedMotion();
  const [value, setValue] = useState(reduced ? target : 0);
  const from = useRef(0);
  useEffect(() => {
    if (reduced) {
      setValue(target);
      from.current = target;
      return undefined;
    }
    if (!inView) return undefined;
    const controls = animate(from.current, target, {
      duration: timing.countUp,
      ease: ease.standard,
      onUpdate: (v) => {
        setValue(v);
      },
    });
    from.current = target;
    return () => {
      controls.stop();
    };
  }, [target, inView, reduced]);
  return [ref, value];
}
