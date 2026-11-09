/** Quick sign-in tab of the developer sandbox: one click opens a session as a seeded demo
 * person, so a demo never stops to type a password. The server only accepts seeded
 * `@devsync.local` clients and developers (never an administrator). */
import { LogIn, ShieldCheck } from "lucide-react";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Avatar, Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { toast } from "@/components/ui/toast-store";
import { pageLoad, safeRedirect } from "@/lib/redirects";
import { useDemoAccounts, useQuickSignIn, type DemoAccount } from "./api";

/** What each person is for in the Demo 1 walkthrough, in the order a demo uses them. */
export const DEMO_PEOPLE: { slug: string; note: string }[] = [
  { slug: "rahim", note: "Client: the ordering project, its plan and the bids" },
  { slug: "nusrat", note: "Experienced React developer: profile and sealed bidding" },
  { slug: "rafsan", note: "Newcomer: takes the role assessment live" },
  { slug: "farzana", note: "Second client: boutique, clinic and school projects" },
  { slug: "arif", note: "Experienced full-stack developer" },
  { slug: "nadia", note: "Newcomer: passed the React assessment" },
  { slug: "lamia", note: "Newcomer: failed the FastAPI assessment" },
  { slug: "mehjabin", note: "Newcomer: passed the Testing assessment" },
  { slug: "shakib", note: "Tester: too slow for the ordering project" },
  { slug: "tahmid", note: "Newcomer: assessment ended early (flagged)" },
];

const slugOf = (email: string): string => email.split("@")[0] ?? email;

function PersonCard({
  account,
  note,
  busy,
  onSignIn,
}: {
  account: DemoAccount;
  note: string;
  busy: boolean;
  onSignIn: (email: string) => void;
}) {
  const first = account.name.split(" ")[0] ?? account.name;
  return (
    <li className="flex items-center gap-3 p-4">
      <Avatar name={account.name} />
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-body-sm font-medium text-text">
          {account.name}
          <Badge tone={account.role === "CLIENT" ? "info" : "neutral"}>
            {account.role === "CLIENT" ? "Client" : "Developer"}
          </Badge>
        </p>
        <p className="mt-0.5 text-body-sm text-text-muted">{note}</p>
      </div>
      <Button
        variant="outline"
        icon={<LogIn aria-hidden="true" />}
        loading={busy}
        onClick={() => {
          onSignIn(account.email);
        }}
        aria-label={`Sign in as ${account.name}`}
      >
        Sign in as {first}
      </Button>
    </li>
  );
}

export function QuickSignIn() {
  const accounts = useDemoAccounts();
  const signIn = useQuickSignIn();
  const off = accounts.error instanceof ApiError && accounts.error.status === 404;

  const go = (email: string) => {
    signIn.mutate(email, {
      onSuccess: (res) => {
        // A full navigation: every cached screen belongs to the person who was signed in before.
        pageLoad.to(safeRedirect(res.redirect_to));
      },
      onError: () => {
        toast({
          tone: "danger",
          title: "Couldn’t sign in",
          description: "Only seeded demo clients and developers can be opened here.",
        });
      },
    });
  };

  if (off) {
    return (
      <Card>
        <EmptyState
          icon={<LogIn aria-hidden="true" />}
          title="Quick sign-in is off here"
          description="It only runs in development and on the offline demo stack."
        />
      </Card>
    );
  }
  if (accounts.isError) {
    return (
      <Card>
        <ErrorState
          title="The demo accounts didn’t load"
          requestId={accounts.error instanceof ApiError ? accounts.error.requestId : null}
          onRetry={() => void accounts.refetch()}
        />
      </Card>
    );
  }
  if (accounts.isPending) {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Loading demo accounts">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  const bySlug = new Map(accounts.data.accounts.map((a) => [slugOf(a.email), a]));
  const planned = DEMO_PEOPLE.flatMap((p) => {
    const account = bySlug.get(p.slug);
    return account ? [{ account, note: p.note }] : [];
  });
  const listed = new Set(planned.map((p) => p.account.email));
  const others = accounts.data.accounts.filter((a) => !listed.has(a.email));
  const busyEmail = signIn.isPending ? signIn.variables : null;

  return (
    <div className="space-y-6">
      <p className="text-body-sm text-text-muted">
        One click signs in as that person and opens their home page. It replaces whoever is signed
        in in this window, so use a private window for a second person.
      </p>
      {planned.length === 0 ? (
        <Card>
          <EmptyState
            icon={<LogIn aria-hidden="true" />}
            title="No demo accounts yet"
            description="Run make demo-up STAGE=1 to load them."
          />
        </Card>
      ) : (
        <Card>
          <CardHeader title="The demo" description="In the order the walkthrough uses them." />
          <ul className="divide-y divide-border">
            {planned.map((p) => (
              <PersonCard
                key={p.account.email}
                account={p.account}
                note={p.note}
                busy={busyEmail === p.account.email}
                onSignIn={go}
              />
            ))}
          </ul>
        </Card>
      )}
      {others.length > 0 ? (
        <Card>
          <CardHeader title="More accounts" />
          <ul className="divide-y divide-border">
            {others.map((a) => (
              <PersonCard
                key={a.email}
                account={a}
                note={a.email}
                busy={busyEmail === a.email}
                onSignIn={go}
              />
            ))}
          </ul>
        </Card>
      ) : null}
      <Card>
        <div className="flex items-start gap-3 p-4">
          <ShieldCheck className="mt-0.5 size-5 shrink-0 text-text-muted" aria-hidden="true" />
          <p className="text-body-sm text-text-muted">
            The administrator needs a code from an authenticator, so there is no shortcut. Use the{" "}
            <Link to="/login" className="text-primary underline-offset-4 hover:underline">
              normal sign-in page
            </Link>{" "}
            with the demo guide’s snippet for the code.
          </p>
        </div>
      </Card>
    </div>
  );
}
