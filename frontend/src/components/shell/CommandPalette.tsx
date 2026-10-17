/**
 * Command palette (spec §13.3): ⌘K / Ctrl+K opens it anywhere in the app; type to filter
 * navigation entries and a few actions; arrows + Enter run one. Project search joins in
 * Phase 5.
 */
import { Command } from "cmdk";
import { CornerDownLeft, Moon, Search, Sun } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { useNavigate } from "react-router";
import type { NavItem } from "@/app/navigation";
import { usePreferences } from "@/design/preferences";

export function useCommandShortcut(onOpen: () => void): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpen();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [onOpen]);
}

function Item({
  children,
  onSelect,
  value,
  keywords,
}: {
  children: ReactNode;
  onSelect: () => void;
  value: string;
  keywords?: string[];
}) {
  return (
    <Command.Item
      value={value}
      {...(keywords ? { keywords } : {})}
      onSelect={onSelect}
      className="group flex min-h-11 cursor-pointer items-center gap-3 rounded-md px-3 text-body-sm text-text data-[selected=true]:bg-surface-2 [&_svg]:size-4 [&_svg]:text-text-muted"
    >
      {children}
      <CornerDownLeft
        className="ml-auto opacity-0 group-data-[selected=true]:opacity-100"
        aria-hidden="true"
      />
    </Command.Item>
  );
}

export function CommandPalette({
  open,
  onOpenChange,
  items,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: NavItem[];
}) {
  const navigate = useNavigate();
  const { resolvedTheme, setTheme } = usePreferences();
  const go = (to: string) => {
    onOpenChange(false);
    void navigate(to);
  };
  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command palette"
      loop
      overlayClassName="anim-overlay fixed inset-0 z-50 bg-[rgb(2_6_23/0.45)] backdrop-blur-[2px]"
      contentClassName="anim-pop fixed left-1/2 top-[12vh] z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-surface shadow-lg"
    >
      <div className="flex items-center gap-3 border-b border-border px-4">
        <Search className="size-4 shrink-0 text-text-muted" aria-hidden="true" />
        <Command.Input
          placeholder="Go to a page or run an action…"
          className="min-h-14 w-full bg-transparent text-body text-text outline-none placeholder:text-text-subtle"
        />
        <kbd className="hidden rounded border border-border px-1.5 py-0.5 font-mono text-caption text-text-muted sm:inline">
          Esc
        </kbd>
      </div>
      <Command.List className="max-h-[min(60vh,420px)] overflow-y-auto p-2">
        <Command.Empty className="px-3 py-8 text-center text-body-sm text-text-muted">
          Nothing matches. Try a page name such as “Settings”.
        </Command.Empty>
        <Command.Group
          heading="Go to"
          className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:text-caption [&_[cmdk-group-heading]]:text-text-muted"
        >
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <Item
                key={item.to}
                value={item.label}
                {...(item.keywords ? { keywords: item.keywords } : {})}
                onSelect={() => {
                  go(item.to);
                }}
              >
                <Icon aria-hidden="true" />
                {item.label}
                {item.phase ? (
                  <span className="text-caption text-text-subtle">
                    Coming in Phase {item.phase}
                  </span>
                ) : null}
              </Item>
            );
          })}
        </Command.Group>
        <Command.Group
          heading="Actions"
          className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:text-caption [&_[cmdk-group-heading]]:text-text-muted"
        >
          <Item
            value={resolvedTheme === "dark" ? "Use light theme" : "Use dark theme"}
            keywords={["theme", "appearance", "dark", "light"]}
            onSelect={() => {
              setTheme(resolvedTheme === "dark" ? "light" : "dark");
              onOpenChange(false);
            }}
          >
            {resolvedTheme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
            {resolvedTheme === "dark" ? "Use light theme" : "Use dark theme"}
          </Item>
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
