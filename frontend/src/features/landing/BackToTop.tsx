import { ArrowUp } from "lucide-react";
import { cn } from "@/lib/cn";
import { useScrollState } from "./useScrollState";

/** "Back to top" after two screens of scrolling (spec §13.11 motion rules). */
export function BackToTop() {
  const { far } = useScrollState();
  return (
    <button
      type="button"
      aria-label="Back to top"
      tabIndex={far ? 0 : -1}
      aria-hidden={far ? undefined : true}
      onClick={() => {
        window.scrollTo({ top: 0 });
        document.getElementById("main")?.focus({ preventScroll: true });
      }}
      className={cn(
        "fixed bottom-[calc(env(safe-area-inset-bottom)+1.25rem)] right-5 z-30 flex size-12 items-center justify-center rounded-full border border-border bg-surface text-text shadow-md transition-[opacity,transform] duration-base",
        far ? "opacity-100" : "pointer-events-none opacity-0 motion-ok:translate-y-2",
      )}
    >
      <ArrowUp className="size-5" aria-hidden="true" />
    </button>
  );
}
