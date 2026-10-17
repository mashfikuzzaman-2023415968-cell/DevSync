/**
 * Theme (light / dark / system) and motion (system / reduce) preferences (spec §13.1,
 * §13.2, Settings §13.5 #19). Stored per device; "system" follows the OS live.
 * The resolved values are mirrored on <html> as `data-theme` and `data-motion`, so CSS
 * (tokens, keyframes) and JavaScript (Framer Motion, the 3D scene) always agree.
 */
import { MotionConfig } from "framer-motion";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { readPref, writePref } from "@/lib/storage";
import type { ThemeName } from "./tokens";

export type ThemePref = "light" | "dark" | "system";
export type MotionPref = "system" | "reduce";

export const THEME_KEY = "ds-theme";
export const MOTION_KEY = "ds-motion";

function media(query: string): MediaQueryList | null {
  return typeof window.matchMedia === "function" ? window.matchMedia(query) : null;
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => media(query)?.matches ?? false);
  useEffect(() => {
    const mq = media(query);
    if (!mq) return undefined;
    const update = () => {
      setMatches(mq.matches);
    };
    update();
    mq.addEventListener("change", update);
    return () => {
      mq.removeEventListener("change", update);
    };
  }, [query]);
  return matches;
}

function readTheme(): ThemePref {
  const v = readPref(THEME_KEY);
  return v === "light" || v === "dark" ? v : "system";
}

function readMotion(): MotionPref {
  return readPref(MOTION_KEY) === "reduce" ? "reduce" : "system";
}

/** Apply the stored theme before React renders (avoids a light flash for dark users). */
export function applyStoredPreferences(): void {
  const theme = readTheme();
  if (theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  if (readMotion() === "reduce") document.documentElement.dataset.motion = "reduce";
}

interface Preferences {
  theme: ThemePref;
  resolvedTheme: ThemeName;
  setTheme: (theme: ThemePref) => void;
  motion: MotionPref;
  reducedMotion: boolean;
  setMotion: (motion: MotionPref) => void;
}

const PreferencesContext = createContext<Preferences | null>(null);

export function PreferencesProvider({
  children,
  nonce,
}: {
  children: ReactNode;
  nonce?: string | undefined;
}) {
  const [theme, setThemeState] = useState<ThemePref>(readTheme);
  const [motion, setMotionState] = useState<MotionPref>(readMotion);
  const osDark = useMediaQuery("(prefers-color-scheme: dark)");
  const osReduced = useMediaQuery("(prefers-reduced-motion: reduce)");
  const resolvedTheme: ThemeName = theme === "system" ? (osDark ? "dark" : "light") : theme;
  const reducedMotion = motion === "reduce" || osReduced;

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    const root = document.documentElement;
    if (reducedMotion) root.dataset.motion = "reduce";
    else delete root.dataset.motion;
  }, [reducedMotion]);

  const setTheme = useCallback((next: ThemePref) => {
    writePref(THEME_KEY, next === "system" ? null : next);
    setThemeState(next);
  }, []);
  const setMotion = useCallback((next: MotionPref) => {
    writePref(MOTION_KEY, next === "system" ? null : next);
    setMotionState(next);
  }, []);

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme, motion, reducedMotion, setMotion }),
    [theme, resolvedTheme, setTheme, motion, reducedMotion, setMotion],
  );
  return (
    <PreferencesContext.Provider value={value}>
      <MotionConfig
        reducedMotion={reducedMotion ? "always" : "never"}
        {...(nonce ? { nonce } : {})}
      >
        {children}
      </MotionConfig>
    </PreferencesContext.Provider>
  );
}

const FALLBACK: Preferences = {
  theme: "system",
  resolvedTheme: "light",
  setTheme: () => undefined,
  motion: "system",
  reducedMotion: false,
  setMotion: () => undefined,
};

export function usePreferences(): Preferences {
  return useContext(PreferencesContext) ?? FALLBACK;
}

/** True when motion must be reduced (OS setting or in-app choice). */
export function useReducedMotion(): boolean {
  return usePreferences().reducedMotion;
}
