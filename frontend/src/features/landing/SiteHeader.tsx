/** Public navbar (spec §13.11 #1). On phones it collapses into a menu button opening a
 * full-height sheet with staggered links. */
import { motion } from "framer-motion";
import { Menu } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Wordmark } from "@/components/brand/Logo";
import { Button, IconButton } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Overlay";
import { useMotion } from "@/design/useMotion";
import { cn } from "@/lib/cn";
import { useScrollState } from "./useScrollState";

export const SECTIONS = [
  { label: "How it works", href: "/#how-it-works" },
  { label: "Features", href: "/#features" },
  { label: "For clients", href: "/#for-clients" },
  { label: "For developers", href: "/#for-developers" },
] as const;

export function SiteHeader({ overlay = false }: { overlay?: boolean }) {
  const { scrolled, hidden } = useScrollState();
  const [open, setOpen] = useState(false);
  const m = useMotion();
  const solid = !overlay || scrolled;
  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-40 pt-[env(safe-area-inset-top)] transition-[background-color,border-color,backdrop-filter,transform] duration-base ease-standard",
        solid
          ? "border-b border-border bg-surface/80 backdrop-blur-md"
          : "border-b border-transparent",
        hidden && !open && "motion-ok:-translate-y-full",
      )}
    >
      <div className="mx-auto flex h-16 max-w-content items-center gap-6 px-4 sm:px-6">
        <Link to="/" className="rounded-md" aria-label="DevSync home">
          <Wordmark />
        </Link>
        <nav aria-label="Main" className="hidden flex-1 items-center gap-1 lg:flex">
          {SECTIONS.map((s) => (
            <a
              key={s.href}
              href={s.href}
              className="rounded-md px-3 py-2 text-body-sm font-medium text-text-muted transition-colors duration-fast hover:text-text"
            >
              {s.label}
            </a>
          ))}
          <Link
            to="/projects"
            className="rounded-md px-3 py-2 text-body-sm font-medium text-text-muted transition-colors duration-fast hover:text-text"
          >
            Browse projects
          </Link>
        </nav>
        <div className="ml-auto hidden items-center gap-2 sm:flex lg:ml-0">
          <Button asChild variant="ghost">
            <Link to="/login">Sign in</Link>
          </Button>
          <Button asChild>
            <Link to="/register">Get started</Link>
          </Button>
        </div>
        <Sheet
          side="bottom"
          full
          open={open}
          onOpenChange={setOpen}
          title="Menu"
          hideTitle
          trigger={
            <IconButton aria-label="Open menu" className="ml-auto lg:hidden sm:ml-0">
              <Menu aria-hidden="true" />
            </IconButton>
          }
        >
          <motion.ul variants={m.list} initial="hidden" animate="show" className="space-y-1">
            {[...SECTIONS, { label: "Browse projects", href: "/projects" }].map((s) => (
              <motion.li key={s.href} variants={m.listItem}>
                {s.href.startsWith("/#") ? (
                  <a
                    href={s.href}
                    onClick={() => {
                      setOpen(false);
                    }}
                    className="flex min-h-14 items-center rounded-md px-3 text-h4 font-semibold text-text hover:bg-surface-2"
                  >
                    {s.label}
                  </a>
                ) : (
                  <Link
                    to={s.href}
                    className="flex min-h-14 items-center rounded-md px-3 text-h4 font-semibold text-text hover:bg-surface-2"
                  >
                    {s.label}
                  </Link>
                )}
              </motion.li>
            ))}
          </motion.ul>
          <div className="mt-8 grid gap-3">
            <Button asChild size="lg">
              <Link to="/register">Get started</Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link to="/login">Sign in</Link>
            </Button>
          </div>
        </Sheet>
      </div>
    </header>
  );
}
