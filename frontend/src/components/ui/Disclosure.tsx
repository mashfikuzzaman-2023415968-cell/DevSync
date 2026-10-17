/** Tabs (active indicator slides between tabs, 180 ms) and Accordion (smooth height),
 * spec §13.2–13.3. Radix provides roving focus and aria wiring. */
import * as AccordionPrimitive from "@radix-ui/react-accordion";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { useId, type ReactNode } from "react";
import { indicatorTransition } from "@/design/motion";
import { useReducedMotion } from "@/design/preferences";
import { cn } from "@/lib/cn";

export interface TabItem {
  value: string;
  label: ReactNode;
  content: ReactNode;
}

export function Tabs({
  items,
  value,
  onValueChange,
  label,
  className,
}: {
  items: TabItem[];
  value: string;
  onValueChange: (value: string) => void;
  label: string;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const layoutId = useId();
  return (
    <TabsPrimitive.Root value={value} onValueChange={onValueChange} className={className}>
      <TabsPrimitive.List
        aria-label={label}
        className="relative flex gap-1 overflow-x-auto border-b border-border [scrollbar-width:thin]"
      >
        {items.map((t) => (
          <TabsPrimitive.Trigger
            key={t.value}
            value={t.value}
            className="relative min-h-11 shrink-0 px-3 text-body-sm font-medium text-text-muted transition-colors duration-fast hover:text-text data-[state=active]:text-text focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
          >
            {t.label}
            {t.value === value ? (
              <motion.span
                layoutId={layoutId}
                transition={indicatorTransition(reduced)}
                className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-primary"
                aria-hidden="true"
              />
            ) : null}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {items.map((t) => (
        <TabsPrimitive.Content key={t.value} value={t.value} className="pt-5 outline-none">
          {t.content}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  );
}

export interface AccordionEntry {
  id: string;
  title: ReactNode;
  content: ReactNode;
}

export function Accordion({ items, className }: { items: AccordionEntry[]; className?: string }) {
  return (
    <AccordionPrimitive.Root
      type="single"
      collapsible
      className={cn("divide-y divide-border", className)}
    >
      {items.map((item) => (
        <AccordionPrimitive.Item key={item.id} value={item.id}>
          <AccordionPrimitive.Header>
            <AccordionPrimitive.Trigger className="group flex min-h-14 w-full items-center justify-between gap-4 py-4 text-left text-body font-medium text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
              {item.title}
              <ChevronDown
                className="size-5 shrink-0 text-text-muted transition-transform duration-base ease-standard group-data-[state=open]:rotate-180"
                aria-hidden="true"
              />
            </AccordionPrimitive.Trigger>
          </AccordionPrimitive.Header>
          <AccordionPrimitive.Content className="accordion-content overflow-hidden text-body text-text-muted">
            <div className="pb-5 pr-8">{item.content}</div>
          </AccordionPrimitive.Content>
        </AccordionPrimitive.Item>
      ))}
    </AccordionPrimitive.Root>
  );
}
