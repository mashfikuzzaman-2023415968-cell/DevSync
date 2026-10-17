/**
 * Form field wrapper (spec §13.3): label, hint, error and required marker wired for screen
 * readers; the field shakes 4 px twice when an error appears (catalogue §13.2) and the
 * message fades in below. Inputs use 16 px text on phones and the right keyboard hints.
 */
import { motion, useAnimationControls } from "framer-motion";
import {
  cloneElement,
  forwardRef,
  isValidElement,
  useEffect,
  useId,
  useRef,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type TextareaHTMLAttributes,
} from "react";
import { useMotion } from "@/design/useMotion";
import { cn } from "@/lib/cn";

export const controlClass =
  "block min-h-11 w-full rounded-md border bg-surface px-3 text-body text-text shadow-xs transition-[border-color,box-shadow] duration-fast placeholder:text-text-subtle hover:border-text-subtle focus-visible:border-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:bg-surface-2 disabled:opacity-70";

interface FieldA11y {
  id: string;
  "aria-invalid"?: true;
  "aria-describedby"?: string;
  "aria-required"?: true;
}

interface FormFieldProps {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | undefined;
  required?: boolean;
  id?: string;
  className?: string;
  /** Visually hide the label (it stays available to screen readers). */
  hideLabel?: boolean;
  /** Extra content on the label row, e.g. a "Forgot password?" link. */
  aside?: ReactNode;
  children: ReactElement<FieldA11y> | ((a11y: FieldA11y) => ReactNode);
}

export function FormField({
  label,
  hint,
  error,
  required = false,
  id,
  className,
  hideLabel = false,
  aside,
  children,
}: FormFieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ");
  const a11y: FieldA11y = {
    id: inputId,
    ...(error ? { "aria-invalid": true as const } : {}),
    ...(describedBy ? { "aria-describedby": describedBy } : {}),
    ...(required ? { "aria-required": true as const } : {}),
  };
  const m = useMotion();
  const controls = useAnimationControls();
  const previous = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (error && error !== previous.current) void controls.start("shake");
    previous.current = error;
  }, [error, controls]);

  const control =
    typeof children === "function"
      ? children(a11y)
      : isValidElement(children)
        ? cloneElement(children, a11y)
        : children;

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className={cn("flex items-baseline justify-between gap-3", hideLabel && "sr-only")}>
        <label htmlFor={inputId} className="block text-body-sm font-medium text-text">
          {label}
          {required ? (
            <span className="ml-0.5 text-danger" aria-hidden="true">
              *
            </span>
          ) : null}
        </label>
        {aside}
      </div>
      <motion.div variants={m.shake} initial="idle" animate={controls}>
        {control}
      </motion.div>
      {hint ? (
        <p id={hintId} className="text-caption text-text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <motion.p
          id={errorId}
          role="alert"
          className="text-caption font-medium text-danger"
          variants={m.swap}
          initial="hidden"
          animate="show"
        >
          {error}
        </motion.p>
      ) : null}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...rest }, ref) {
    const invalid = rest["aria-invalid"] === true || rest["aria-invalid"] === "true";
    return (
      <input
        ref={ref}
        {...rest}
        className={cn(controlClass, invalid ? "border-danger" : "border-border", className)}
      />
    );
  },
);

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  /** Show "n / max" under the box (spec §13.3 Textarea with counter). */
  counter?: boolean;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, counter = false, maxLength, value, defaultValue, ...rest },
  ref,
) {
  const invalid = rest["aria-invalid"] === true || rest["aria-invalid"] === "true";
  const length = String(value ?? defaultValue ?? "").length;
  return (
    <div>
      <textarea
        ref={ref}
        {...rest}
        value={value}
        defaultValue={defaultValue}
        maxLength={maxLength}
        className={cn(
          controlClass,
          "min-h-24 py-2.5",
          invalid ? "border-danger" : "border-border",
          className,
        )}
      />
      {counter && maxLength ? (
        <p
          className={cn(
            "mt-1 text-right text-caption tabular",
            length >= maxLength ? "text-danger" : "text-text-muted",
          )}
          aria-live="polite"
        >
          {length} / {maxLength}
        </p>
      ) : null}
    </div>
  );
});

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: ReactNode;
  error?: string | undefined;
  aside?: ReactNode;
}

/** Labelled text input: the common case of FormField + Input. */
export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, hint, error, id, required, aside, className, ...rest },
  ref,
) {
  return (
    <FormField
      label={label}
      hint={hint}
      error={error}
      required={required === true}
      aside={aside}
      {...(id ? { id } : {})}
    >
      <Input ref={ref} {...rest} required={required} className={className} />
    </FormField>
  );
});
