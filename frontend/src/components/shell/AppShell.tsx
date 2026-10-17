/**
 * App shell (spec §13.4, §13.14):
 * - ≥ 1024 px: 64 px top bar + sidebar 248 px, collapsible to a 72 px icon rail (remembered
 *   per user on this device);
 * - 768–1023 px: the sidebar is an icon rail;
 * - < 768 px: compact top bar + bottom tab bar with four destinations; "More" opens a
 *   full-height sheet with the rest.
 * Content is centred at max 1280 px with 24 px (32 px ≥ 1280) padding; pages fade + rise
 * 6 px on navigation while the sidebar stays still.
 */
import { motion } from "framer-motion";
import {
  Bell,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  Sun,
  UserRound,
} from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import type { NavItem } from "@/app/navigation";
import { Wordmark } from "@/components/brand/Logo";
import { IconButton } from "@/components/ui/Button";
import { Avatar } from "@/components/ui/Display";
import { DropdownMenu, Sheet, Tooltip } from "@/components/ui/Overlay";
import { useMediaQuery, usePreferences } from "@/design/preferences";
import { useMotion } from "@/design/useMotion";
import { useLogout, useMe } from "@/features/auth/api";
import { cn } from "@/lib/cn";
import { readPref, writePref } from "@/lib/storage";
import { CommandPalette, useCommandShortcut } from "./CommandPalette";

export interface ShellNav {
  home: string;
  sidebar: NavItem[];
  tabs: NavItem[];
  profilePath?: string;
}

function isActive(pathname: string, item: NavItem, home: string): boolean {
  if (item.to === home) return pathname === home;
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
}

function useSidebar(userId: string | undefined) {
  const key = `ds-sidebar:${userId ?? "anon"}`;
  const [collapsed, setCollapsed] = useState(() => readPref(key) === "collapsed");
  // The user id arrives after the first render; read that user's choice when it does.
  useEffect(() => {
    setCollapsed(readPref(key) === "collapsed");
  }, [key]);
  const toggle = useCallback(() => {
    setCollapsed((c) => {
      writePref(key, c ? null : "collapsed");
      return !c;
    });
  }, [key]);
  return { collapsed, toggle };
}

function SidebarLink({
  item,
  active,
  rail,
  tooltip,
}: {
  item: NavItem;
  active: boolean;
  /** Icon-only presentation: always (collapsed) or below 1024 px only. */
  rail: "always" | "lg";
  /** Show the label as a tooltip (only while icons stand alone). */
  tooltip: boolean;
}) {
  const Icon = item.icon;
  const link = (
    <NavLink
      to={item.to}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex min-h-11 items-center gap-3 rounded-md px-3 text-body-sm font-medium transition-colors duration-fast",
        active
          ? "bg-primary-soft text-primary"
          : "text-text-muted hover:bg-surface-2 hover:text-text",
        rail === "always" && "justify-center px-0",
        rail === "lg" && "md:justify-center md:px-0 lg:justify-start lg:px-3",
      )}
    >
      {active ? (
        <span
          className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary"
          aria-hidden="true"
        />
      ) : null}
      <Icon className="size-5 shrink-0" aria-hidden="true" />
      <span
        className={cn(
          "truncate transition-opacity duration-page",
          rail === "always" && "sr-only",
          rail === "lg" && "md:sr-only lg:not-sr-only",
        )}
      >
        {item.label}
      </span>
    </NavLink>
  );
  return tooltip ? <Tooltip content={item.label}>{link}</Tooltip> : link;
}

function AccountMenu({ profilePath }: { profilePath: string }) {
  const me = useMe();
  const navigate = useNavigate();
  const logout = useLogout(false, () => void navigate("/", { replace: true }));
  const { resolvedTheme, setTheme } = usePreferences();
  const name = me.data?.display_name ?? "Account";
  return (
    <DropdownMenu
      label={
        <span className="block">
          <span className="block text-body-sm font-semibold text-text">{name}</span>
          <span className="block truncate">{me.data?.email}</span>
        </span>
      }
      trigger={
        <button
          type="button"
          aria-label="Account menu"
          className="inline-flex size-11 items-center justify-center rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <Avatar name={name} size="sm" />
        </button>
      }
      items={[
        {
          label: "Profile",
          icon: <UserRound aria-hidden="true" />,
          onSelect: () => void navigate(profilePath),
        },
        {
          label: "Settings",
          icon: <Settings aria-hidden="true" />,
          onSelect: () => void navigate("/settings"),
        },
        {
          label: resolvedTheme === "dark" ? "Light theme" : "Dark theme",
          icon: resolvedTheme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />,
          onSelect: () => {
            setTheme(resolvedTheme === "dark" ? "light" : "dark");
          },
        },
        "separator",
        {
          label: "Sign out",
          icon: <LogOut aria-hidden="true" />,
          onSelect: () => {
            logout.mutate();
          },
        },
      ]}
    />
  );
}

export function AppShell({ nav, children }: { nav: ShellNav; children?: ReactNode }) {
  const me = useMe();
  const location = useLocation();
  const navigate = useNavigate();
  const logout = useLogout(false, () => void navigate("/", { replace: true }));
  const m = useMotion();
  const { collapsed, toggle } = useSidebar(me.data?.id);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const openPalette = useCallback(() => {
    setPaletteOpen(true);
  }, []);
  useCommandShortcut(openPalette);
  const profilePath = nav.profilePath ?? "/settings";
  const rail = collapsed ? "always" : "lg";
  const wide = useMediaQuery("(min-width: 1024px)");
  const tabPaths = new Set(nav.tabs.map((t) => t.to));

  return (
    <div className="min-h-dvh bg-bg">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[80] focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:shadow-md"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-border bg-surface/90 pt-[env(safe-area-inset-top)] backdrop-blur supports-[backdrop-filter]:bg-surface/80">
        <div className="flex h-16 items-center gap-2 px-3 sm:px-4">
          <Link
            to={nav.home}
            className="inline-flex min-h-11 items-center rounded-md px-1"
            aria-label="DevSync home"
          >
            <Wordmark />
          </Link>
          <button
            type="button"
            onClick={openPalette}
            className="ml-4 hidden min-h-11 w-full max-w-md items-center gap-2 rounded-md border border-border bg-bg px-3 text-body-sm text-text-muted transition-colors duration-fast hover:border-text-subtle md:flex"
          >
            <Search className="size-4" aria-hidden="true" />
            <span>Search or jump to…</span>
            <kbd className="ml-auto rounded border border-border bg-surface px-1.5 font-mono text-caption">
              Ctrl K
            </kbd>
          </button>
          <div className="ml-auto flex items-center gap-1">
            <IconButton
              aria-label="Search or jump to a page"
              className="md:hidden"
              onClick={openPalette}
            >
              <Search aria-hidden="true" />
            </IconButton>
            <IconButton
              aria-label="Notifications"
              onClick={() => {
                void navigate("/notifications");
              }}
            >
              <Bell aria-hidden="true" />
            </IconButton>
            <AccountMenu profilePath={profilePath} />
          </div>
        </div>
      </header>

      <div className="flex">
        <aside
          aria-label="Main navigation"
          className={cn(
            "sticky top-16 hidden h-[calc(100dvh-4rem)] shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-page ease-standard md:flex",
            collapsed ? "w-[72px]" : "w-[72px] lg:w-[248px]",
          )}
        >
          <nav className="flex-1 space-y-1 overflow-y-auto p-3">
            {nav.sidebar.map((item) => (
              <SidebarLink
                key={item.to}
                item={item}
                active={isActive(location.pathname, item, nav.home)}
                rail={rail}
                tooltip={collapsed || !wide}
              />
            ))}
          </nav>
          <div className="hidden border-t border-border p-3 lg:block">
            <button
              type="button"
              onClick={toggle}
              aria-pressed={collapsed}
              className={cn(
                "flex min-h-11 w-full items-center gap-3 rounded-md px-3 text-body-sm text-text-muted transition-colors duration-fast hover:bg-surface-2 hover:text-text",
                collapsed && "justify-center px-0",
              )}
            >
              {collapsed ? (
                <PanelLeftOpen className="size-5" aria-hidden="true" />
              ) : (
                <PanelLeftClose className="size-5" aria-hidden="true" />
              )}
              <span className={cn(collapsed && "sr-only")}>
                {collapsed ? "Expand sidebar" : "Collapse sidebar"}
              </span>
            </button>
          </div>
        </aside>

        <main
          id="main"
          tabIndex={-1}
          className="min-w-0 flex-1 px-4 pb-28 pt-6 outline-none sm:px-6 md:pb-12 xl:px-8"
        >
          <motion.div
            key={location.pathname}
            variants={m.page}
            initial="hidden"
            animate="show"
            className="mx-auto max-w-content"
          >
            {children ?? <Outlet />}
          </motion.div>
        </main>
      </div>

      <nav
        aria-label="Quick navigation"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        <ul className="grid grid-cols-4">
          {nav.tabs.map((item) => {
            const Icon = item.icon;
            const active = isActive(location.pathname, item, nav.home);
            return (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex min-h-14 flex-col items-center justify-center gap-0.5 text-caption font-medium",
                    active ? "text-primary" : "text-text-muted",
                  )}
                >
                  <Icon className="size-5" aria-hidden="true" />
                  {item.label}
                </NavLink>
              </li>
            );
          })}
          <li>
            <Sheet
              side="bottom"
              full
              open={moreOpen}
              onOpenChange={setMoreOpen}
              title="More"
              trigger={
                <button
                  type="button"
                  className="flex min-h-14 w-full flex-col items-center justify-center gap-0.5 text-caption font-medium text-text-muted"
                >
                  <Menu className="size-5" aria-hidden="true" />
                  More
                </button>
              }
            >
              <ul className="space-y-1">
                {nav.sidebar
                  .filter((item) => !tabPaths.has(item.to))
                  .map((item) => {
                    const Icon = item.icon;
                    return (
                      <li key={item.to}>
                        <NavLink
                          to={item.to}
                          onClick={() => {
                            setMoreOpen(false);
                          }}
                          className="flex min-h-12 items-center gap-3 rounded-md px-3 text-body text-text hover:bg-surface-2"
                        >
                          <Icon className="size-5 text-text-muted" aria-hidden="true" />
                          {item.label}
                        </NavLink>
                      </li>
                    );
                  })}
                <li className="border-t border-border pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setMoreOpen(false);
                      logout.mutate();
                    }}
                    className="flex min-h-12 w-full items-center gap-3 rounded-md px-3 text-body text-danger hover:bg-danger-bg"
                  >
                    <LogOut className="size-5" aria-hidden="true" />
                    Sign out
                  </button>
                </li>
              </ul>
            </Sheet>
          </li>
        </ul>
      </nav>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} items={nav.sidebar} />
    </div>
  );
}
