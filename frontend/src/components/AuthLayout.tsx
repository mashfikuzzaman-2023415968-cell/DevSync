import type { ReactNode } from "react";
import { Link } from "react-router";

/** DevSync mark: a small team of linked nodes, one amber (the newcomer). The same motif
 * becomes the 3D constellation on the homepage in Phase 2 (spec §13.12–13.13). */
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <path
        d="M10 11 22 11 16 22Z"
        fill="none"
        className="stroke-on-primary"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="10" cy="11" r="3" className="fill-on-primary" />
      <circle cx="22" cy="11" r="3" className="fill-on-primary" />
      <circle cx="16" cy="22" r="3" className="fill-newcomer-bg" />
    </svg>
  );
}

const LOOP = [
  ["Plan", "Break the work into milestones and see the critical path."],
  ["Hire a fair team", "Balanced on skill, teamwork, time and cost, with room for newcomers."],
  ["Watch the work", "Progress, risks and deadline impact, without surveillance."],
  ["Pay by milestone", "Money is held in escrow and released on approval."],
  ["Learn from it", "What actually happened shapes the next team."],
] as const;

/** Split auth screen: the form on the left, DevSync's loop on wide screens. */
export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-dvh bg-bg lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:shadow-md"
      >
        Skip to content
      </a>
      <div className="flex flex-col px-4 py-6 sm:px-10">
        <header className="flex items-center justify-between">
          <Link
            to="/"
            className="flex items-center gap-2 rounded-md text-h4 font-semibold text-text"
          >
            <Mark />
            <span>DevSync</span>
          </Link>
          <Link to="/" className="text-body-sm text-text-muted hover:text-text">
            Back to home
          </Link>
        </header>
        <main id="main" className="flex flex-1 items-center py-10">
          <div className="w-full max-w-[400px]">
            <h1 className="text-h3 font-semibold tracking-tight text-text">{title}</h1>
            {subtitle ? <p className="mt-2 text-body text-text-muted">{subtitle}</p> : null}
            <div className="mt-8">{children}</div>
          </div>
        </main>
      </div>
      <aside
        className="hidden border-l border-border bg-surface px-10 py-16 lg:block"
        aria-label="How DevSync works"
      >
        <p className="text-lead font-semibold text-text">One loop, from plan to reputation</p>
        <ol className="mt-8 space-y-6">
          {LOOP.map(([step, text], i) => (
            <li key={step} className="flex gap-4">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary-soft text-body-sm font-semibold text-primary tabular">
                {i + 1}
              </span>
              <span>
                <span className="block text-body-sm font-semibold text-text">{step}</span>
                <span className="block text-body-sm text-text-muted">{text}</span>
              </span>
            </li>
          ))}
        </ol>
      </aside>
    </div>
  );
}
