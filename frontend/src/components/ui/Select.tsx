/** Select (Radix) and searchable Combobox (Popover + cmdk), spec §13.3. */
import * as PopoverPrimitive from "@radix-ui/react-popover";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Command } from "cmdk";
import { Check, ChevronDown, ChevronsUpDown } from "lucide-react";
import { forwardRef, useState } from "react";
import { cn } from "@/lib/cn";
import { readNonce } from "@/lib/nonce";

function nonceProp(): { nonce?: string } {
  const nonce = readNonce();
  return nonce ? { nonce } : {};
}
import { controlClass } from "./Field";

export interface Option {
  value: string;
  label: string;
}

interface SelectProps {
  value: string | undefined;
  onChange: (value: string) => void;
  options: readonly Option[];
  placeholder?: string;
  id?: string;
  disabled?: boolean;
  "aria-invalid"?: true;
  "aria-describedby"?: string;
  "aria-label"?: string;
}

export const Select = forwardRef<HTMLButtonElement, SelectProps>(function Select(
  { value, onChange, options, placeholder = "Choose…", disabled, ...a11y },
  ref,
) {
  return (
    <SelectPrimitive.Root
      {...(value !== undefined ? { value } : {})}
      onValueChange={onChange}
      {...(disabled !== undefined ? { disabled } : {})}
    >
      <SelectPrimitive.Trigger
        ref={ref}
        {...a11y}
        className={cn(
          controlClass,
          "flex items-center justify-between gap-2 text-left data-[placeholder]:text-text-subtle",
          a11y["aria-invalid"] ? "border-danger" : "border-border",
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon>
          <ChevronDown className="size-4 text-text-muted" aria-hidden="true" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={6}
          className="anim-pop z-50 max-h-[min(var(--radix-select-content-available-height),320px)] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border border-border bg-surface shadow-lg"
        >
          {/* Radix adds a <style> here to hide the scrollbar; the per-response nonce lets it
              through the strict CSP (D23). */}
          <SelectPrimitive.Viewport className="p-1" {...nonceProp()}>
            {options.map((o) => (
              <SelectPrimitive.Item
                key={o.value}
                value={o.value}
                className="relative flex min-h-10 cursor-pointer select-none items-center rounded-md py-2 pl-8 pr-3 text-body-sm text-text outline-none data-[highlighted]:bg-surface-2 data-[state=checked]:font-medium"
              >
                <SelectPrimitive.ItemIndicator className="absolute left-2 inline-flex">
                  <Check className="size-4 text-primary" aria-hidden="true" />
                </SelectPrimitive.ItemIndicator>
                <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
});

interface ComboboxProps {
  value: string | undefined;
  onChange: (value: string) => void;
  options: readonly Option[];
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  id?: string;
  "aria-invalid"?: true;
  "aria-describedby"?: string;
}

/** Combobox: a button opening a searchable list (keyboard: type, arrows, Enter). */
export function Combobox({
  value,
  onChange,
  options,
  placeholder = "Choose…",
  searchPlaceholder = "Search…",
  emptyText = "No matches. Try a shorter search.",
  ...a11y
}: ComboboxProps) {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.value === value);
  return (
    <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
      <PopoverPrimitive.Trigger
        {...a11y}
        role="combobox"
        aria-expanded={open}
        className={cn(
          controlClass,
          "flex items-center justify-between gap-2 text-left",
          selected ? "" : "text-text-subtle",
          a11y["aria-invalid"] ? "border-danger" : "border-border",
        )}
      >
        <span className="truncate">{selected?.label ?? placeholder}</span>
        <ChevronsUpDown className="size-4 shrink-0 text-text-muted" aria-hidden="true" />
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          sideOffset={6}
          align="start"
          className="anim-pop z-50 w-[var(--radix-popover-trigger-width)] min-w-56 overflow-hidden rounded-lg border border-border bg-surface shadow-lg"
        >
          <Command loop>
            <Command.Input
              placeholder={searchPlaceholder}
              className="w-full border-b border-border bg-surface px-3 py-2.5 text-body text-text outline-none placeholder:text-text-subtle"
            />
            <Command.List className="max-h-64 overflow-auto p-1">
              <Command.Empty className="px-3 py-6 text-center text-body-sm text-text-muted">
                {emptyText}
              </Command.Empty>
              {options.map((o) => (
                <Command.Item
                  key={o.value}
                  value={o.label}
                  onSelect={() => {
                    onChange(o.value);
                    setOpen(false);
                  }}
                  className="flex min-h-10 cursor-pointer items-center gap-2 rounded-md px-3 text-body-sm text-text data-[selected=true]:bg-surface-2"
                >
                  <Check
                    className={cn(
                      "size-4 text-primary",
                      o.value === value ? "opacity-100" : "opacity-0",
                    )}
                    aria-hidden="true"
                  />
                  {o.label}
                </Command.Item>
              ))}
            </Command.List>
          </Command>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
