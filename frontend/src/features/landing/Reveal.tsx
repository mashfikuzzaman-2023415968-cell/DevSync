/** Section reveal (spec §13.11 motion rules): fade + 16 px rise once when 20% visible,
 * children staggered 60 ms; never re-animates. Reduced motion: short fade only. */
import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { useMotion } from "@/design/useMotion";

export function Reveal({
  children,
  className,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "li" | "ul";
}) {
  const m = useMotion();
  const Tag = motion[as];
  return (
    <Tag
      className={className}
      variants={m.reveal}
      // Reduced motion: content is simply there, no scroll trigger needed.
      initial={m.reduced ? false : "hidden"}
      whileInView="show"
      viewport={{ once: true, amount: 0.2 }}
    >
      {children}
    </Tag>
  );
}

/** A child of Reveal that takes part in the stagger. */
export function RevealItem({ children, className }: { children: ReactNode; className?: string }) {
  const m = useMotion();
  return (
    <motion.div className={className} variants={m.reveal}>
      {children}
    </motion.div>
  );
}
