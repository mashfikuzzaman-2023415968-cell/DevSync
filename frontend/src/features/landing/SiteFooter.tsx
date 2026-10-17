/** Footer (spec §13.11 #11): logo and tagline, link columns, course credit, copyright. */
import { Link } from "react-router";
import { Wordmark } from "@/components/brand/Logo";

const COLUMNS = [
  {
    title: "Product",
    links: [
      { label: "How it works", to: "/#how-it-works" },
      { label: "Features", to: "/#features" },
      { label: "Browse projects", to: "/projects" },
      { label: "FAQ", to: "/#faq" },
    ],
  },
  {
    title: "For clients",
    links: [
      { label: "Hire a team", to: "/register?role=client" },
      { label: "Why DevSync", to: "/#for-clients" },
    ],
  },
  {
    title: "For developers",
    links: [
      { label: "Find work", to: "/register?role=developer" },
      { label: "Fair first chance", to: "/#fairness" },
    ],
  },
  {
    title: "Research",
    links: [{ label: "The papers behind DevSync", to: "/#research" }],
  },
  {
    title: "Legal",
    links: [
      { label: "Privacy", to: "/privacy" },
      { label: "Terms of use", to: "/terms" },
    ],
  },
] as const;

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-surface pb-[env(safe-area-inset-bottom)]">
      <div className="mx-auto grid max-w-content gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,5fr)]">
        <div>
          <Wordmark />
          <p className="mt-3 max-w-xs text-body-sm text-text-muted">
            Plan software projects, hire fair teams of freelance developers and pay by milestone.
          </p>
        </div>
        <nav aria-label="Footer" className="grid grid-cols-2 gap-8 sm:grid-cols-3 lg:grid-cols-5">
          {COLUMNS.map((col) => (
            <div key={col.title}>
              <h2 className="text-body-sm font-semibold text-text">{col.title}</h2>
              <ul className="mt-3 space-y-1">
                {col.links.map((l) => (
                  <li key={l.label}>
                    {l.to.startsWith("/#") ? (
                      <a
                        href={l.to}
                        className="inline-flex min-h-11 min-w-11 items-center text-body-sm text-text-muted hover:text-text"
                      >
                        {l.label}
                      </a>
                    ) : (
                      <Link
                        to={l.to}
                        className="inline-flex min-h-11 min-w-11 items-center text-body-sm text-text-muted hover:text-text"
                      >
                        {l.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </div>
      <div className="border-t border-border">
        <div className="mx-auto flex max-w-content flex-col gap-2 px-4 py-6 text-caption text-text-muted sm:flex-row sm:justify-between sm:px-6">
          <p>
            A CSE 3102 project, Department of Computer Science and Engineering, University of Dhaka.
          </p>
          <p>© 2026 DevSync. Payments on DevSync are simulated.</p>
        </div>
      </div>
    </footer>
  );
}
