/** Slider with a visible value label and keyboard steps (spec §13.3); thumbs are 28 px on
 * touch screens (§13.14). */
import * as SliderPrimitive from "@radix-ui/react-slider";
import { useId, type ReactNode } from "react";
import { cn } from "@/lib/cn";

interface SliderProps {
  label: ReactNode;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  /** How the value is shown and announced, e.g. (v) => `${v}%`. */
  format?: (value: number) => string;
  disabled?: boolean;
  className?: string;
}

export function Slider({
  label,
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  format = String,
  disabled = false,
  className,
}: SliderProps) {
  const labelId = useId();
  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <span id={labelId} className="text-body-sm font-medium text-text">
          {label}
        </span>
        <span className="text-body-sm font-semibold tabular text-text" aria-hidden="true">
          {format(value)}
        </span>
      </div>
      <SliderPrimitive.Root
        value={[value]}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onValueChange={(v) => {
          if (v[0] !== undefined) onChange(v[0]);
        }}
        className="relative flex h-7 w-full touch-none select-none items-center data-[disabled]:opacity-55"
      >
        <SliderPrimitive.Track className="relative h-1.5 grow overflow-hidden rounded-full bg-surface-2">
          <SliderPrimitive.Range className="absolute h-full bg-primary" />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb
          aria-labelledby={labelId}
          aria-valuetext={format(value)}
          className="block size-7 rounded-full border-2 border-primary bg-surface shadow-sm transition-shadow duration-fast hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary md:size-5"
        />
      </SliderPrimitive.Root>
    </div>
  );
}
