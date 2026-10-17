import { useEffect, useState } from "react";
import { timing } from "@/design/motion";
import { useReducedMotion } from "@/design/preferences";

/** Steps 0..count-1 on a loop while `active`; rests on the last step before starting over.
 * Reduced motion: stays on the final step (spec §13.11: show final states). */
export function useLoop(count: number, active: boolean): number {
  const reduced = useReducedMotion();
  const [step, setStep] = useState(reduced ? count - 1 : 0);
  useEffect(() => {
    if (reduced) {
      setStep(count - 1);
      return undefined;
    }
    if (!active) return undefined;
    const delay = step === count - 1 ? timing.loopRestMs : timing.loopStepMs;
    const id = window.setTimeout(() => {
      setStep((s) => (s + 1) % count);
    }, delay);
    return () => {
      window.clearTimeout(id);
    };
  }, [step, count, active, reduced]);
  return step;
}
