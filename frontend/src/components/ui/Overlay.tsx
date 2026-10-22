/**
 * Overlays (spec §13.3, catalogue §13.2): Dialog (overlay fade 180 ms, panel scale 0.96 → 1),
 * AlertDialog for destructive confirmations, Sheet (slides from the right; a bottom sheet
 * with a drag handle on phones, §13.14), Popover, Tooltip (also opens on focus and tap) and
 * DropdownMenu. Radix handles focus trapping, Escape and aria wiring.
 */
import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as DropdownPrimitive from "@radix-ui/react-dropdown-menu";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Button } from "./Button";

const overlayClass = "anim-overlay fixed inset-0 z-50 bg-[rgb(2_6_23/0.45)] backdrop-blur-[2px]";

interface DialogProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  trigger?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
}

function controlled(open: boolean | undefined, onOpenChange: ((o: boolean) => void) | undefined) {
  return {
    ...(open !== undefined ? { open } : {}),
    ...(onOpenChange ? { onOpenChange } : {}),
  };
}

export function Dialog({
  open,
  onOpenChange,
  trigger,
  title,
  description,
  children,
  footer,
  size = "md",
}: DialogProps) {
  return (
    <DialogPrimitive.Root {...controlled(open, onOpenChange)}>
      {trigger ? <DialogPrimitive.Trigger asChild>{trigger}</DialogPrimitive.Trigger> : null}
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className={overlayClass} />
        <DialogPrimitive.Content
          {...(description ? {} : { "aria-describedby": undefined })}
          className={cn(
            "anim-pop fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-border bg-surface shadow-lg",
            size === "sm" && "max-w-sm",
            size === "md" && "max-w-lg",
            size === "lg" && "max-w-2xl",
          )}
        >
          <div className="flex items-start justify-between gap-4 px-6 pt-6">
            <div>
              <DialogPrimitive.Title className="text-h4 font-semibold text-text">
                {title}
              </DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="mt-1 text-body-sm text-text-muted">
                  {description}
                </DialogPrimitive.Description>
              ) : null}
            </div>
            <DialogPrimitive.Close
              className="-mr-2 -mt-2 inline-flex size-11 shrink-0 items-center justify-center rounded-full text-text-muted transition-colors duration-fast hover:bg-surface-2 hover:text-text"
              aria-label="Close"
            >
              <X className="size-5" aria-hidden="true" />
            </DialogPrimitive.Close>
          </div>
          <div className="overflow-y-auto px-6 py-4">{children}</div>
          {footer ? (
            <div className="flex flex-col-reverse gap-2 border-t border-border px-6 py-4 sm:flex-row sm:justify-end">
              {footer}
            </div>
          ) : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

interface ConfirmProps {
  trigger: ReactNode;
  title: ReactNode;
  /** What will happen — destructive actions explain their consequences (spec §13.6). */
  description: ReactNode;
  confirmLabel: string;
  onConfirm: () => void | Promise<void>;
  /** When set, the person must type this text to enable the button (e.g. "DELETE"). */
  confirmText?: string;
  destructive?: boolean;
}

export function ConfirmDialog({
  trigger,
  title,
  description,
  confirmLabel,
  onConfirm,
  confirmText,
  destructive = true,
}: ConfirmProps) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const ready = !confirmText || typed === confirmText;
  return (
    <AlertDialogPrimitive.Root
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setTyped("");
      }}
    >
      <AlertDialogPrimitive.Trigger asChild>{trigger}</AlertDialogPrimitive.Trigger>
      <AlertDialogPrimitive.Portal>
        <AlertDialogPrimitive.Overlay className={overlayClass} />
        <AlertDialogPrimitive.Content className="anim-pop fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-lg">
          <AlertDialogPrimitive.Title className="text-h4 font-semibold text-text">
            {title}
          </AlertDialogPrimitive.Title>
          <AlertDialogPrimitive.Description className="mt-2 text-body-sm text-text-muted">
            {description}
          </AlertDialogPrimitive.Description>
          {confirmText ? (
            <label className="mt-4 block text-body-sm text-text">
              Type <span className="font-mono font-semibold">{confirmText}</span> to confirm
              <input
                value={typed}
                onChange={(e) => {
                  setTyped(e.target.value);
                }}
                autoComplete="off"
                className="mt-1.5 block min-h-11 w-full rounded-md border border-border bg-surface px-3 text-body text-text"
              />
            </label>
          ) : null}
          <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <AlertDialogPrimitive.Cancel asChild>
              <Button variant="outline">Cancel</Button>
            </AlertDialogPrimitive.Cancel>
            <Button
              variant={destructive ? "destructive" : "primary"}
              disabled={!ready}
              loading={busy}
              onClick={() => {
                setBusy(true);
                void Promise.resolve(onConfirm()).finally(() => {
                  setBusy(false);
                  setOpen(false);
                });
              }}
            >
              {confirmLabel}
            </Button>
          </div>
        </AlertDialogPrimitive.Content>
      </AlertDialogPrimitive.Portal>
    </AlertDialogPrimitive.Root>
  );
}

interface SheetProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  trigger?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  /** right: side sheet; bottom: phone sheet with handle; left: navigation drawer. */
  side?: "right" | "bottom" | "left";
  /** Full height (menus, "More" sheets). */
  full?: boolean;
  hideTitle?: boolean;
}

export function Sheet({
  open,
  onOpenChange,
  trigger,
  title,
  description,
  children,
  footer,
  side = "right",
  full = false,
  hideTitle = false,
}: SheetProps) {
  return (
    <DialogPrimitive.Root {...controlled(open, onOpenChange)}>
      {trigger ? <DialogPrimitive.Trigger asChild>{trigger}</DialogPrimitive.Trigger> : null}
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className={overlayClass} />
        <DialogPrimitive.Content
          {...(description ? {} : { "aria-describedby": undefined })}
          className={cn(
            "fixed z-50 flex flex-col border-border bg-surface shadow-lg",
            side === "right" &&
              "anim-sheet-right inset-y-0 right-0 w-full max-w-md border-l pb-[env(safe-area-inset-bottom)]",
            side === "left" &&
              "anim-sheet-left inset-y-0 left-0 w-[min(320px,85vw)] border-r pb-[env(safe-area-inset-bottom)]",
            side === "bottom" &&
              cn(
                "anim-sheet-bottom inset-x-0 bottom-0 rounded-t-xl border-t pb-[max(env(safe-area-inset-bottom),16px)]",
                full ? "top-[max(env(safe-area-inset-top),16px)]" : "max-h-[85dvh]",
              ),
          )}
        >
          {side === "bottom" ? (
            <div className="mx-auto mt-2 h-1.5 w-10 rounded-full bg-border" aria-hidden="true" />
          ) : null}
          <div className="flex items-start justify-between gap-4 px-5 pt-4">
            <div className={cn(hideTitle && "sr-only")}>
              <DialogPrimitive.Title className="text-h4 font-semibold text-text">
                {title}
              </DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="mt-1 text-body-sm text-text-muted">
                  {description}
                </DialogPrimitive.Description>
              ) : null}
            </div>
            <DialogPrimitive.Close
              className="ml-auto inline-flex size-11 shrink-0 items-center justify-center rounded-full text-text-muted transition-colors duration-fast hover:bg-surface-2 hover:text-text"
              aria-label="Close"
            >
              <X className="size-5" aria-hidden="true" />
            </DialogPrimitive.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
          {footer ? (
            <div className="sticky bottom-0 flex gap-2 border-t border-border bg-surface px-5 py-3">
              {footer}
            </div>
          ) : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export const SheetClose = DialogPrimitive.Close;

export function Popover({
  trigger,
  children,
  align = "center",
}: {
  trigger: ReactNode;
  children: ReactNode;
  align?: "start" | "center" | "end";
}) {
  return (
    <PopoverPrimitive.Root>
      <PopoverPrimitive.Trigger asChild>{trigger}</PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          align={align}
          sideOffset={8}
          className="anim-pop z-50 w-72 rounded-lg border border-border bg-surface p-4 text-body-sm text-text shadow-lg"
        >
          {children}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}

export const TooltipProvider = TooltipPrimitive.Provider;

/** Tooltip: hover or keyboard focus opens it; a tap toggles it too (no hover-only info). */
export function Tooltip({ content, children }: { content: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <TooltipPrimitive.Provider delayDuration={300}>
      <TooltipPrimitive.Root open={open} onOpenChange={setOpen}>
        <TooltipPrimitive.Trigger
          asChild
          onClick={() => {
            setOpen((o) => !o);
          }}
        >
          {children}
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            sideOffset={6}
            className="anim-pop z-50 max-w-64 rounded-md bg-text px-2.5 py-1.5 text-caption text-bg shadow-md"
          >
            {content}
            <TooltipPrimitive.Arrow className="fill-text" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}

export interface MenuItem {
  label: string;
  icon?: ReactNode;
  onSelect: () => void;
  destructive?: boolean;
}

export function DropdownMenu({
  trigger,
  items,
  label,
  align = "end",
}: {
  trigger: ReactNode;
  items: (MenuItem | "separator")[];
  label?: ReactNode;
  align?: "start" | "end";
}) {
  return (
    <DropdownPrimitive.Root>
      <DropdownPrimitive.Trigger asChild>{trigger}</DropdownPrimitive.Trigger>
      <DropdownPrimitive.Portal>
        <DropdownPrimitive.Content
          align={align}
          sideOffset={6}
          className="anim-pop z-50 min-w-52 rounded-lg border border-border bg-surface p-1 shadow-lg"
        >
          {label ? (
            <DropdownPrimitive.Label className="px-3 py-2 text-caption text-text-muted">
              {label}
            </DropdownPrimitive.Label>
          ) : null}
          {items.map((item, i) =>
            item === "separator" ? (
              <DropdownPrimitive.Separator
                key={`sep-${String(i)}`}
                className="my-1 h-px bg-border"
              />
            ) : (
              <DropdownPrimitive.Item
                key={item.label}
                onSelect={item.onSelect}
                className={cn(
                  "flex min-h-10 cursor-pointer select-none items-center gap-2.5 rounded-md px-3 text-body-sm outline-none data-[highlighted]:bg-surface-2 [&_svg]:size-4",
                  item.destructive ? "text-danger" : "text-text",
                )}
              >
                {item.icon}
                {item.label}
              </DropdownPrimitive.Item>
            ),
          )}
        </DropdownPrimitive.Content>
      </DropdownPrimitive.Portal>
    </DropdownPrimitive.Root>
  );
}
