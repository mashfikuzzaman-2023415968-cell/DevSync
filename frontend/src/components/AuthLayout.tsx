/**
 * Auth screens layout (spec §13.5 #2–5, §13.11 navigation rules): the DevSync logo links home,
 * "Back to home" is always there, the form sits left; on wide screens a side panel shows the
 * constellation still (softly blurred, §13.13) and DevSync's loop.
 */
import type { ReactNode } from "react";
import { Link } from "react-router";
import { Wordmark } from "@/components/brand/Logo";
import { Still } from "@/components/brand/Still";

export { Mark } from "@/components/brand/Logo";

const LOOP = [
  ["Plan", "Milestones, dependencies and the critical path."],
  ["Hire a fair team", "Balanced on skill, teamwork, time and cost, with room for newcomers."],
  ["Watch the work", "Progress, risks and deadline impact, without surveillance."],
  ["Pay by milestone", "Escrow released when you approve the work."],
  ["Learn from it", "What happened shapes the next team."],
] as const;

export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="min-h-dvh bg-bg lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,480px)]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:shadow-md"
      >
        Skip to content
      </a>
      <div className="flex min-h-dvh flex-col px-4 pb-[max(env(safe-area-inset-bottom),24px)] pt-[max(env(safe-area-inset-top),20px)] sm:px-10">
        <header className="flex items-center justify-between">
          <Link to="/" className="rounded-md" aria-label="DevSync home">
            <Wordmark />
          </Link>
          <Link
            to="/"
            className="inline-flex min-h-11 items-center rounded-md px-2 text-body-sm text-text-muted hover:text-text"
          >
            Back to home
          </Link>
        </header>
        <main
          id="main"
          className="flex flex-1 items-center justify-center py-10 lg:justify-start lg:pl-[8%]"
        >
          <div className="w-full max-w-[420px]">
            <h1 className="text-h2 font-semibold tracking-tight text-text">{title}</h1>
            {subtitle ? <p className="mt-2 text-body text-text-muted">{subtitle}</p> : null}
            <div className="mt-8">{children}</div>
          </div>
        </main>
      </div>
      <aside
        className="relative hidden overflow-hidden border-l border-border bg-surface lg:flex lg:flex-col lg:justify-end"
        aria-label="How DevSync works"
      >
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-gradient-to-b from-primary-soft via-surface to-surface"
        />
        <Still
          name="team"
          className="absolute -right-16 top-10 w-[560px] max-w-none opacity-80 blur-[1.5px]"
        />
        <div className="relative px-10 pb-14">
          <p className="text-lead font-semibold text-text">One loop, from plan to reputation</p>
          <ol className="mt-6 space-y-4">
            {LOOP.map(([step, text], i) => (
              <li key={step} className="flex gap-4">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary-soft text-body-sm font-semibold tabular text-primary">
                  {i + 1}
                </span>
                <span>
                  <span className="block text-body-sm font-semibold text-text">{step}</span>
                  <span className="block text-body-sm text-text-muted">{text}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      </aside>
    </div>
  );
}
