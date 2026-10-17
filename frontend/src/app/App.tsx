import type React from "react";

/**
 * Phase 0 placeholder shell. Phase 2 replaces it with the router, app shell and
 * the homepage (spec §13.11). It already follows the page rules: one h1, a skip
 * link, landmarks, tokens only (no ad-hoc colours).
 */
export function App(): React.JSX.Element {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:shadow-md"
      >
        Skip to content
      </a>
      <header className="mx-auto flex max-w-content items-center gap-3 px-6 py-6">
        <Wordmark />
      </header>
      <main id="main" className="mx-auto max-w-content px-6 pb-24 pt-16">
        <p className="text-body-sm font-medium uppercase tracking-wide text-primary">
          Foundations ready
        </p>
        <h1 className="mt-3 max-w-3xl text-h2 font-semibold tracking-tight md:text-h1">
          Plan the project. Hire a fair team. Watch the work. Learn from it.
        </h1>
        <p className="mt-4 max-w-2xl text-lead text-text-muted">
          DevSync is being built phase by phase. This page confirms that the secure edge, the API
          and the design tokens are wired together.
        </p>
        <section
          aria-labelledby="status-heading"
          className="mt-10 max-w-xl rounded-lg border border-border bg-surface p-6 shadow-xs"
        >
          <h2 id="status-heading" className="text-h4 font-semibold">
            Platform status
          </h2>
          <ul className="mt-4 space-y-2 text-body-sm text-text-muted">
            <li>HTTPS with strict security headers</li>
            <li>API health checks and structured logs</li>
            <li>Append-only, hash-chained audit log</li>
          </ul>
        </section>
      </main>
    </>
  );
}

function Wordmark(): React.JSX.Element {
  return (
    <span className="flex items-center gap-2 text-h4 font-semibold" role="img" aria-label="DevSync">
      <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
        <rect width="32" height="32" rx="8" fill="var(--primary)" />
        <circle cx="10" cy="11" r="3" fill="var(--on-primary)" />
        <circle cx="22" cy="11" r="3" fill="var(--on-primary)" />
        <circle cx="16" cy="22" r="3" fill="var(--newcomer-bg)" />
      </svg>
      <span aria-hidden="true">DevSync</span>
    </span>
  );
}
