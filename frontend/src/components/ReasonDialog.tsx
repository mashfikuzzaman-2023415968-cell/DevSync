/**
 * A dialog that asks for a reason before an action (leave, decline, lead change, reject): the
 * text area counts characters, the action stays disabled until the length is right, and the
 * server's message appears inline if it refuses.
 */
import { useState, type ReactNode } from "react";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { FormField, Textarea } from "@/components/ui/Field";
import { Dialog } from "@/components/ui/Overlay";
import { textLength } from "@/lib/text";

export function ReasonDialog({
  trigger,
  title,
  description,
  label,
  actionLabel,
  min = 20,
  max = 500,
  optional = false,
  destructive = false,
  onSubmit,
}: {
  trigger: ReactNode;
  title: string;
  description: ReactNode;
  label: string;
  actionLabel: string;
  min?: number;
  max?: number;
  optional?: boolean;
  destructive?: boolean;
  onSubmit: (reason: string) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const length = textLength(reason.trim());
  const ok = (optional && length === 0) || (length >= min && length <= max);
  const hint = optional
    ? `Optional, up to ${String(max)} characters.`
    : `Between ${String(min)} and ${String(max)} characters.`;
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) {
          setReason("");
          setError(null);
        }
      }}
      trigger={trigger}
      title={title}
      description={description}
      footer={
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button
            variant="outline"
            onClick={() => {
              setOpen(false);
            }}
          >
            Cancel
          </Button>
          <Button
            variant={destructive ? "destructive" : "primary"}
            disabled={!ok}
            loading={busy}
            onClick={() => {
              setBusy(true);
              setError(null);
              onSubmit(reason.trim())
                .then(() => {
                  setOpen(false);
                })
                .catch((e: unknown) => {
                  setError(e instanceof ApiError ? e.message : "That didn’t work. Try again.");
                })
                .finally(() => {
                  setBusy(false);
                });
            }}
          >
            {actionLabel}
          </Button>
        </div>
      }
    >
      <FormField label={label} hint={hint} error={error ?? undefined} required={!optional}>
        <Textarea
          value={reason}
          onChange={(e) => {
            setReason(e.target.value);
          }}
          maxLength={max}
          counter
          rows={4}
        />
      </FormField>
    </Dialog>
  );
}
