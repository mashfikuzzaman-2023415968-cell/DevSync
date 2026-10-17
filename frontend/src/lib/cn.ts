/** Class name helper: clsx for conditions + tailwind-merge for conflicts (shadcn/ui style).
 * The merge config knows DevSync's own type scale so `text-body` (size) and `text-text`
 * (colour) never cancel each other out. */
import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

const merge = extendTailwindMerge({
  extend: {
    theme: {
      text: ["caption", "body-sm", "body", "lead", "h4", "h3", "h2", "h1", "hero"],
      radius: ["sm", "md", "lg", "xl"],
      shadow: ["xs", "sm", "md", "lg"],
    },
  },
});

export function cn(...inputs: ClassValue[]): string {
  return merge(clsx(inputs));
}
