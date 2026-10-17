/** Privacy and terms (linked from the homepage footer and registration, spec §13.11).
 * Plain-language course-project wording; payments are simulated. */
import type { ReactNode } from "react";
import { Link } from "react-router";
import { Wordmark } from "@/components/brand/Logo";

function LegalLayout({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-dvh bg-bg">
      <header className="mx-auto flex max-w-content items-center justify-between px-4 py-5 sm:px-6">
        <Link to="/" className="rounded-md" aria-label="DevSync home">
          <Wordmark />
        </Link>
        <Link
          to="/"
          className="min-h-11 rounded-md px-3 py-2.5 text-body-sm text-text-muted hover:text-text"
        >
          Back to home
        </Link>
      </header>
      <main id="main" className="mx-auto max-w-2xl px-4 pb-24 pt-8 sm:px-6">
        <h1 className="text-h1 font-semibold tracking-tight text-text">{title}</h1>
        <p className="mt-2 text-body-sm text-text-muted">Last updated {updated}</p>
        <div className="mt-10 space-y-8 text-body text-text-muted [&_h2]:mb-2 [&_h2]:text-h4 [&_h2]:font-semibold [&_h2]:text-text">
          {children}
        </div>
      </main>
    </div>
  );
}

export function PrivacyPage() {
  return (
    <LegalLayout title="Privacy" updated="17 Oct 2026">
      <section>
        <h2>What we collect</h2>
        <p>
          Your name, email, mobile number and the work you do on DevSync: projects, bids, tasks,
          reviews and payment records. We store a hashed version of your password, never the
          password itself.
        </p>
      </section>
      <section>
        <h2>Why</h2>
        <p>
          To run the service: verify accounts, form teams, show progress to the people on your
          project, calculate reputation from real work and keep the platform safe from fraud.
        </p>
      </section>
      <section>
        <h2>Monitoring, not surveillance</h2>
        <p>
          DevSync looks at work evidence such as tasks, check-ins and deliverables. It never records
          your screen, keystrokes or location.
        </p>
      </section>
      <section>
        <h2>Your choices</h2>
        <p>
          You can see and sign out of every device in Settings and change your name or password at
          any time. This is a university course project (CSE 3102, University of Dhaka); data is
          used only to run and evaluate it.
        </p>
      </section>
    </LegalLayout>
  );
}

export function TermsPage() {
  return (
    <LegalLayout title="Terms of use" updated="17 Oct 2026">
      <section>
        <h2>Payments are simulated</h2>
        <p>
          DevSync is a university course project. Wallets, escrow and payouts use simulated money;
          no real payment is ever taken or sent.
        </p>
      </section>
      <section>
        <h2>One person, one account</h2>
        <p>
          Each account belongs to one real person with a verified phone number. Don’t share
          accounts, create fake ones or post reviews about your own work.
        </p>
      </section>
      <section>
        <h2>Fair play</h2>
        <p>
          Bids are sealed until teams are formed. Collusion, shill bidding and review manipulation
          are checked automatically and reviewed by an administrator.
        </p>
      </section>
    </LegalLayout>
  );
}
