/** Checkbox, radio group and switch (spec §13.3) on Radix primitives: keyboard support,
 * focus-visible rings, 44 px touch rows, labels always attached. */
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import * as RadioGroupPrimitive from "@radix-ui/react-radio-group";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import { Check, Minus } from "lucide-react";
import { forwardRef, useId, type ComponentPropsWithoutRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";

const focus =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

type CheckboxProps = ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root> & {
  label: ReactNode;
  description?: ReactNode;
};

export const Checkbox = forwardRef<HTMLButtonElement, CheckboxProps>(function Checkbox(
  { label, description, className, id, ...rest },
  ref,
) {
  const autoId = useId();
  const boxId = id ?? autoId;
  return (
    <div className={cn("flex min-h-11 items-start gap-3 py-1", className)}>
      <CheckboxPrimitive.Root
        ref={ref}
        id={boxId}
        {...rest}
        className={cn(
          "peer mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-sm border border-text-subtle bg-surface transition-colors duration-fast data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary text-on-primary disabled:opacity-55",
          focus,
        )}
      >
        <CheckboxPrimitive.Indicator>
          {rest.checked === "indeterminate" ? (
            <Minus className="size-3.5" strokeWidth={3} aria-hidden="true" />
          ) : (
            <Check className="size-3.5" strokeWidth={3} aria-hidden="true" />
          )}
        </CheckboxPrimitive.Indicator>
      </CheckboxPrimitive.Root>
      <label
        htmlFor={boxId}
        className="cursor-pointer text-body-sm text-text peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
      >
        {label}
        {description ? (
          <span className="mt-0.5 block text-caption text-text-muted">{description}</span>
        ) : null}
      </label>
    </div>
  );
});

export interface RadioOption {
  value: string;
  label: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
}

type RadioGroupProps = Omit<
  ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Root>,
  "children"
> & {
  options: RadioOption[];
  legend: ReactNode;
  hideLegend?: boolean;
  /** Large selectable cards instead of compact rows (role choice, test answers). */
  cards?: boolean;
};

export function RadioGroup({
  options,
  legend,
  hideLegend = false,
  cards = false,
  className,
  ...rest
}: RadioGroupProps) {
  const base = useId();
  return (
    <fieldset className={className}>
      <legend className={cn("mb-2 text-body-sm font-medium text-text", hideLegend && "sr-only")}>
        {legend}
      </legend>
      <RadioGroupPrimitive.Root {...rest} className={cn(cards ? "grid gap-3" : "space-y-1")}>
        {options.map((o) => {
          const id = `${base}-${o.value}`;
          return (
            <label
              key={o.value}
              htmlFor={id}
              className={cn(
                "group flex min-h-11 cursor-pointer items-start gap-3",
                cards &&
                  "rounded-lg border border-border bg-surface p-4 shadow-xs transition-[border-color,background-color,box-shadow,transform] duration-base ease-standard hover:border-primary/40 hover:shadow-sm has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-primary-soft has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary motion-ok:hover:-translate-y-0.5",
                o.disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <RadioGroupPrimitive.Item
                id={id}
                value={o.value}
                disabled={o.disabled}
                className={cn(
                  "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-text-subtle bg-surface transition-colors duration-fast data-[state=checked]:border-primary",
                  !cards && focus,
                  cards && "focus-visible:outline-none",
                )}
              >
                <RadioGroupPrimitive.Indicator className="size-2.5 rounded-full bg-primary" />
              </RadioGroupPrimitive.Item>
              <span className="min-w-0">
                <span
                  className={cn("block text-body-sm text-text", cards && "text-body font-semibold")}
                >
                  {o.label}
                </span>
                {o.description ? (
                  <span className="mt-0.5 block text-body-sm text-text-muted">{o.description}</span>
                ) : null}
              </span>
            </label>
          );
        })}
      </RadioGroupPrimitive.Root>
    </fieldset>
  );
}

type SwitchProps = ComponentPropsWithoutRef<typeof SwitchPrimitive.Root> & {
  label: ReactNode;
  description?: ReactNode;
};

export const Switch = forwardRef<HTMLButtonElement, SwitchProps>(function Switch(
  { label, description, className, id, ...rest },
  ref,
) {
  const autoId = useId();
  const switchId = id ?? autoId;
  return (
    <div className={cn("flex min-h-11 items-center justify-between gap-4", className)}>
      <label htmlFor={switchId} className="cursor-pointer text-body-sm text-text">
        {label}
        {description ? (
          <span className="mt-0.5 block text-caption text-text-muted">{description}</span>
        ) : null}
      </label>
      <SwitchPrimitive.Root
        ref={ref}
        id={switchId}
        {...rest}
        className={cn(
          "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full bg-border transition-colors duration-base data-[state=checked]:bg-primary disabled:opacity-55",
          focus,
        )}
      >
        <SwitchPrimitive.Thumb className="block size-5 translate-x-0.5 rounded-full bg-surface shadow-sm transition-transform duration-base ease-standard data-[state=checked]:translate-x-[22px]" />
      </SwitchPrimitive.Root>
    </div>
  );
});
