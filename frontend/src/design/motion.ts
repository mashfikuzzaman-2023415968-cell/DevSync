/**
 * Motion system (spec §13.2): the only place with durations, easings and springs.
 * Components use these variants; an ESLint rule rejects numeric durations elsewhere.
 * Every variant has a reduced form (opacity only, ≤ 120 ms) used when the OS or the
 * in-app setting asks for reduced motion (§13.2, §13.11).
 */
import type { Transition, Variants } from "framer-motion";

export const duration = { fast: 0.12, base: 0.18, slow: 0.28, page: 0.22 } as const;
/** Milliseconds for timers and CSS (same values). */
export const durationMs = {
  fast: 120,
  base: 180,
  slow: 280,
  page: 220,
  press: 80,
  crossfade: 400,
} as const;

export const ease = {
  standard: [0.2, 0, 0, 1],
  emphasized: [0.3, 0, 0, 1],
  exit: [0.4, 0, 1, 1],
} as const satisfies Record<string, [number, number, number, number]>;

export const spring = { drag: { type: "spring", stiffness: 500, damping: 35 } } as const;

export const stagger = { list: 0.03, maxItems: 8, words: 0.04, reveal: 0.06 } as const;

/** Longer, one-off timings from the catalogue (count-ups, meters, reveals, highlights). */
export const timing = {
  countUp: 0.6,
  meter: 0.4,
  reveal: 0.35,
  highlightFade: 1.2,
  crossFade: 0.4,
  toastMs: 5000,
  /** Homepage showcase loops: one step every 1.4 s, then a 2.8 s rest. */
  loopStepMs: 1400,
  loopRestMs: 2800,
  shakeX: 4,
  /** Press-and-hold before a touch drag starts, so scrolling still works. */
  dragHoldMs: 150,
} as const;

/** No animation (reduced motion or a fixed final state). */
export const instant = { duration: 0 } as const satisfies Transition;

const reducedFade: Transition = { duration: duration.fast, ease: ease.standard };

function pick(reduced: boolean, full: Variants, fade: Variants = FADE): Variants {
  return reduced ? fade : full;
}

const FADE: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: reducedFade },
  exit: { opacity: 0, transition: reducedFade },
};

/** All catalogue variants for the current motion preference. */
export function motionVariants(reduced: boolean) {
  return {
    /** Page transitions: fade + 6 px rise, 220 ms. */
    page: pick(reduced, {
      hidden: { opacity: 0, y: 6 },
      show: { opacity: 1, y: 0, transition: { duration: duration.page, ease: ease.standard } },
      exit: { opacity: 0, transition: { duration: duration.fast, ease: ease.exit } },
    }),
    /** Cards entering: fade + 8 px rise, 180 ms. */
    card: pick(reduced, {
      hidden: { opacity: 0, y: 8 },
      show: { opacity: 1, y: 0, transition: { duration: duration.base, ease: ease.standard } },
    }),
    /** Lists: children stagger 30 ms (first 8 items). */
    list: pick(
      reduced,
      { hidden: {}, show: { transition: { staggerChildren: stagger.list } } },
      { hidden: {}, show: {} },
    ),
    listItem: pick(reduced, {
      hidden: { opacity: 0, y: 4 },
      show: { opacity: 1, y: 0, transition: { duration: duration.base, ease: ease.standard } },
    }),
    /** Homepage section reveal: fade + 16 px rise, 350 ms, children 60 ms apart. */
    reveal: pick(reduced, {
      hidden: { opacity: 0, y: 16 },
      show: {
        opacity: 1,
        y: 0,
        transition: {
          duration: timing.reveal,
          ease: ease.standard,
          staggerChildren: stagger.reveal,
        },
      },
    }),
    /** Hero headline (§13.11 #2): the heading rises 8 px while its words appear one by one
     * (40 ms stagger, blur 4 px → 0). Words stay inline so the heading is one text block and
     * remains the Largest Contentful Paint element. */
    words: pick(
      reduced,
      {
        hidden: { y: 8 },
        show: {
          y: 0,
          transition: {
            staggerChildren: stagger.words,
            duration: duration.slow * 2,
            ease: ease.emphasized,
          },
        },
      },
      { hidden: {}, show: {} },
    ),
    word: pick(
      reduced,
      {
        hidden: { opacity: 0, filter: "blur(4px)" },
        show: {
          opacity: 1,
          filter: "blur(0px)",
          transition: { duration: duration.slow, ease: ease.emphasized },
        },
      },
      { hidden: { opacity: 1 }, show: { opacity: 1 } },
    ),
    /** Dialog: overlay fade 180 ms; panel scale 0.96 → 1 + fade. */
    overlay: pick(reduced, {
      hidden: { opacity: 0 },
      show: { opacity: 1, transition: { duration: duration.base } },
      exit: { opacity: 0, transition: { duration: duration.fast, ease: ease.exit } },
    }),
    dialog: pick(reduced, {
      hidden: { opacity: 0, scale: 0.96 },
      show: { opacity: 1, scale: 1, transition: { duration: duration.base, ease: ease.standard } },
      exit: { opacity: 0, scale: 0.96, transition: { duration: duration.fast, ease: ease.exit } },
    }),
    /** Side sheet from the right, 280 ms emphasized; bottom sheet from below on mobile. */
    sheetRight: pick(reduced, {
      hidden: { x: "100%" },
      show: { x: 0, transition: { duration: duration.slow, ease: ease.emphasized } },
      exit: { x: "100%", transition: { duration: duration.base, ease: ease.exit } },
    }),
    sheetBottom: pick(reduced, {
      hidden: { y: "100%" },
      show: { y: 0, transition: { duration: duration.slow, ease: ease.emphasized } },
      exit: { y: "100%", transition: { duration: duration.base, ease: ease.exit } },
    }),
    /** Form error: shake 4 px twice (150 ms). */
    shake: pick(
      reduced,
      {
        idle: { x: 0 },
        shake: {
          x: [0, -timing.shakeX, timing.shakeX, -timing.shakeX, timing.shakeX, 0],
          transition: { duration: 0.15 * 2, ease: "linear" },
        },
      },
      { idle: { x: 0 }, shake: { x: 0 } },
    ),
    /** Cross-fade between swapped contents (toggles, tab panels). */
    swap: FADE,
  } satisfies Record<string, Variants>;
}

export type MotionVariants = ReturnType<typeof motionVariants>;

/** Transition for animated widths (progress bars, meters): 400 ms emphasized. */
export function meterTransition(reduced: boolean): Transition {
  return reduced ? instant : { duration: timing.meter, ease: ease.emphasized };
}

/** Sliding indicators (tabs, segmented controls): 180 ms. */
export function indicatorTransition(reduced: boolean): Transition {
  return reduced ? instant : { duration: duration.base, ease: ease.standard };
}
