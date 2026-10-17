import { Link, Navigate } from "react-router";
import { Mark } from "@/components/AuthLayout";
import { useMe } from "@/features/auth/api";
import { roleHome } from "@/lib/redirects";

/** Entry point (spec §13.11). The full homepage with the 3D hero is built in Phase 2;
 * this keeps the rules now: guests land here, signed-in users go to their home. */
export default function HomePage() {
  const me = useMe();
  if (me.data) return <Navigate to={roleHome(me.data.role, me.data.status)} replace />;
  return (
    <div className="min-h-dvh bg-bg">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:shadow-md"
      >
        Skip to content
      </a>
      <header className="mx-auto flex max-w-content items-center justify-between px-4 py-5 sm:px-6">
        <span className="flex items-center gap-2 text-h4 font-semibold text-text">
          <Mark />
          <span>DevSync</span>
        </span>
        <nav aria-label="Main" className="flex items-center gap-2">
          <Link
            to="/login"
            className="min-h-11 rounded-md px-3 py-2.5 text-body-sm font-medium text-text"
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className="min-h-11 rounded-md bg-primary px-4 py-2.5 text-body-sm font-semibold text-on-primary hover:bg-primary-hover"
          >
            Get started
          </Link>
        </nav>
      </header>
      <main id="main" className="mx-auto max-w-content px-4 pb-24 pt-16 sm:px-6">
        <h1 className="max-w-3xl text-h2 font-semibold tracking-tight text-text md:text-h1">
          Plan the project. Hire a fair team. Watch the work. Learn from it.
        </h1>
        <p className="mt-4 max-w-2xl text-lead text-text-muted">
          DevSync plans software projects, forms balanced teams of freelance developers, including
          newcomers, and turns what really happened into fairer reputations.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            to="/register?role=client"
            className="min-h-11 rounded-md bg-primary px-5 py-2.5 text-body font-semibold text-on-primary hover:bg-primary-hover"
          >
            Hire a team
          </Link>
          <Link
            to="/register?role=developer"
            className="min-h-11 rounded-md border border-border bg-surface px-5 py-2.5 text-body font-semibold text-text hover:bg-surface-2"
          >
            Find work
          </Link>
        </div>
      </main>
    </div>
  );
}
