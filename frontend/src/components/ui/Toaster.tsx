/** Toasts (catalogue §13.2): slide in from the bottom right, auto-dismiss after 5 s with a
 * progress bar, pause on hover/focus, swipe to dismiss; announced politely (§13.6). */
import * as ToastPrimitive from "@radix-ui/react-toast";
import { CircleAlert, CircleCheck, Info, TriangleAlert, X } from "lucide-react";
import { timing } from "@/design/motion";
import { cn } from "@/lib/cn";
import { dismissToast, useToasts, type ToastTone } from "./toast-store";

const TONE: Record<ToastTone, { icon: typeof Info; className: string; label: string }> = {
  info: { icon: Info, className: "text-info", label: "Note" },
  success: { icon: CircleCheck, className: "text-success", label: "Done" },
  warning: { icon: TriangleAlert, className: "text-warning", label: "Warning" },
  danger: { icon: CircleAlert, className: "text-danger", label: "Problem" },
};

export function Toaster() {
  const toasts = useToasts();
  return (
    <ToastPrimitive.Provider duration={timing.toastMs} swipeDirection="right">
      {toasts.map((t) => {
        const tone = TONE[t.tone];
        const Icon = tone.icon;
        return (
          <ToastPrimitive.Root
            key={t.id}
            onOpenChange={(open) => {
              if (!open) dismissToast(t.id);
            }}
            className="anim-toast group relative flex w-full items-start gap-3 overflow-hidden rounded-lg border border-border bg-surface p-4 pr-12 shadow-lg"
          >
            <Icon className={cn("mt-0.5 size-5 shrink-0", tone.className)} aria-hidden="true" />
            <div className="min-w-0">
              <ToastPrimitive.Title className="text-body-sm font-semibold text-text">
                <span className="sr-only">{tone.label}: </span>
                {t.title}
              </ToastPrimitive.Title>
              {t.description ? (
                <ToastPrimitive.Description className="mt-0.5 text-body-sm text-text-muted">
                  {t.description}
                </ToastPrimitive.Description>
              ) : null}
            </div>
            <ToastPrimitive.Close
              aria-label="Dismiss"
              className="absolute right-1.5 top-1.5 inline-flex size-11 items-center lg:size-9 justify-center rounded-full text-text-muted hover:bg-surface-2 hover:text-text"
            >
              <X className="size-4" aria-hidden="true" />
            </ToastPrimitive.Close>
            <span
              aria-hidden="true"
              className={cn(
                "absolute inset-x-0 bottom-0 h-0.5 origin-left animate-[ds-progress_5s_linear_forwards] group-hover:[animation-play-state:paused] group-focus-within:[animation-play-state:paused]",
                t.tone === "danger" ? "bg-danger" : "bg-primary",
              )}
            />
          </ToastPrimitive.Root>
        );
      })}
      <ToastPrimitive.Viewport className="fixed bottom-[calc(env(safe-area-inset-bottom)+5rem)] right-0 z-[60] flex w-full max-w-sm flex-col gap-2 p-4 outline-none md:bottom-0" />
    </ToastPrimitive.Provider>
  );
}
