import type { ReactNode } from "react";

type Tone = "danger" | "success" | "info" | "warning";

const TONES: Record<Tone, { box: string; icon: string; label: string }> = {
  danger: { box: "bg-danger-bg text-danger", icon: "!", label: "Error" },
  success: { box: "bg-success-bg text-success", icon: "✓", label: "Done" },
  info: { box: "bg-info-bg text-info", icon: "i", label: "Note" },
  warning: { box: "bg-warning-bg text-warning", icon: "!", label: "Warning" },
};

/** Status message with an icon and a text label, never colour alone (spec §13.6). */
export function Alert({ tone, children }: { tone: Tone; children: ReactNode }) {
  const t = TONES[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={`flex gap-3 rounded-md px-3 py-2.5 text-body-sm ${t.box}`}
    >
      <span
        aria-hidden="true"
        className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-current text-caption font-bold"
      >
        {t.icon}
      </span>
      <span>
        <span className="sr-only">{t.label}: </span>
        {children}
      </span>
    </div>
  );
}
