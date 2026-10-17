import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import { Mark } from "@/components/AuthLayout";
import { Button } from "@/components/ui/Button";
import { useLogout, useMe } from "@/features/auth/api";
import { roleHome } from "@/lib/redirects";

/** Minimal signed-in frame (the full app shell arrives in Phase 2, spec §13.4). */
export function AppFrame({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  return (
    <div className="min-h-dvh bg-bg">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:shadow-md"
      >
        Skip to content
      </a>
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex h-16 max-w-content items-center justify-between px-4 sm:px-6">
          <Link
            to={roleHome(me.data?.role, me.data?.status)}
            className="flex items-center gap-2 rounded-md text-h4 font-semibold text-text"
          >
            <Mark />
            <span>DevSync</span>
          </Link>
          <nav aria-label="Account" className="flex items-center gap-2">
            <Link
              to="/settings"
              className="min-h-11 rounded-md px-3 py-2.5 text-body-sm text-text-muted hover:text-text"
            >
              Settings
            </Link>
            <Button
              variant="secondary"
              loading={logout.isPending}
              onClick={() => {
                logout.mutate(undefined, {
                  onSettled: () => void navigate("/", { replace: true }),
                });
              }}
            >
              Sign out
            </Button>
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-content px-4 py-8 sm:px-6">
        <h1 className="text-h3 font-semibold tracking-tight text-text">{title}</h1>
        {description ? <p className="mt-1 text-body text-text-muted">{description}</p> : null}
        <div className="mt-6">{children}</div>
      </main>
    </div>
  );
}
