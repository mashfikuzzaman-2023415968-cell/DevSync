import { useMemo } from "react";
import { motionVariants, type MotionVariants } from "./motion";
import { useReducedMotion } from "./preferences";

/** Catalogue variants for the current motion preference (spec §13.2). */
export function useMotion(): MotionVariants & { reduced: boolean } {
  const reduced = useReducedMotion();
  return useMemo(() => ({ ...motionVariants(reduced), reduced }), [reduced]);
}
