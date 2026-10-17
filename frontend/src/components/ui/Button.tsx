/**
 * Button (spec §13.3, catalogue §13.2): primary, secondary, outline, ghost, destructive,
 * link; sizes sm/md/lg; hover lifts 1 px with a shadow, press scales to 0.98; loading
 * cross-fades the label to a spinner without changing the width. One primary per view
 * (§13.8). Icon-only buttons use IconButton, which requires an aria-label.
 */
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Spinner } from "./Spinner";

export const buttonVariants = cva(
  "relative inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-semibold transition-[background-color,color,box-shadow,transform,border-color] duration-fast ease-standard disabled:pointer-events-none disabled:opacity-55 aria-disabled:pointer-events-none aria-disabled:opacity-55 motion-ok:active:scale-[0.98] motion-ok:active:duration-press [&_svg]:size-5 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "bg-primary text-on-primary shadow-xs hover:bg-primary-hover hover:shadow-sm motion-ok:hover:-translate-y-px",
        secondary:
          "bg-surface-2 text-text hover:bg-border/70 motion-ok:hover:-translate-y-px hover:shadow-xs",
        outline:
          "border border-border bg-surface text-text shadow-xs hover:border-text-subtle hover:shadow-sm motion-ok:hover:-translate-y-px",
        ghost: "text-text hover:bg-surface-2",
        destructive:
          "bg-danger text-on-danger shadow-xs hover:shadow-sm hover:brightness-95 motion-ok:hover:-translate-y-px",
        link: "h-auto min-h-0 px-0 text-primary underline-offset-4 hover:underline",
      },
      size: {
        sm: "min-h-9 px-3 text-body-sm [&_svg]:size-4",
        md: "min-h-11 px-4 text-body-sm",
        lg: "min-h-12 px-6 text-body",
      },
    },
    compoundVariants: [{ variant: "link", className: "min-h-0 px-0" }],
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  loading?: boolean;
  full?: boolean;
  /** Render the child element (e.g. a router Link) with button styles. */
  asChild?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant,
    size,
    loading = false,
    full = false,
    asChild = false,
    icon,
    className,
    children,
    disabled,
    type,
    ...rest
  },
  ref,
) {
  const classes = cn(buttonVariants({ variant, size }), full && "w-full", className);
  if (asChild) {
    return (
      <Slot ref={ref} className={classes} {...rest}>
        {children}
      </Slot>
    );
  }
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      {...rest}
      disabled={disabled === true || loading}
      aria-busy={loading || undefined}
      className={classes}
    >
      <span
        className={cn(
          "inline-flex items-center gap-2 transition-opacity duration-fast",
          loading && "opacity-0",
        )}
      >
        {icon}
        {children}
      </span>
      {loading ? (
        <span className="absolute inset-0 flex items-center justify-center">
          <Spinner />
        </span>
      ) : null}
    </button>
  );
});

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> {
  /** Required: icon-only buttons need an accessible name (spec §13.3, §13.8 #7). */
  "aria-label": string;
  size?: "sm" | "md";
  tone?: "default" | "inverse";
}

/** Icon-only button: a soft circle fades in on hover (120 ms); 44 px target on touch. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { className, size = "md", tone = "default", type, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      {...rest}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full transition-colors duration-fast disabled:pointer-events-none disabled:opacity-55 [&_svg]:size-5",
        size === "md" ? "size-11" : "size-9 [&_svg]:size-4",
        tone === "default"
          ? "text-text-muted hover:bg-surface-2 hover:text-text"
          : "text-on-primary hover:bg-white/15",
        className,
      )}
    >
      {children}
    </button>
  );
});
