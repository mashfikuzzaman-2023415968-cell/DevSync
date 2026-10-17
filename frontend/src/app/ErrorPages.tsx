/** Error and placeholder pages (spec §13.5 #8): 403, 404, 500 with the request id,
 * maintenance, and the route error boundary that reports to /client-errors. */
import { Construction, Home } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { isRouteErrorResponse, Link, useRouteError } from "react-router";
import { ApiError } from "@/api/client";
import { NodeArt } from "@/components/brand/NodeArt";
import { Wordmark } from "@/components/brand/Logo";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Display";
import { EmptyState, PageHeader } from "@/components/ui/Feedback";
import { reportClientError } from "@/lib/reportError";

function StandalonePage({
  code,
  title,
  description,
  children,
}: {
  code?: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <header className="mx-auto flex w-full max-w-content items-center px-4 py-5 sm:px-6">
        <Link to="/" className="rounded-md" aria-label="DevSync home">
          <Wordmark />
        </Link>
      </header>
      <main id="main" className="flex flex-1 items-center justify-center px-4 pb-16">
        <div className="flex max-w-md flex-col items-center text-center">
          <NodeArt className="h-28" />
          {code ? (
            <p className="mt-6 font-mono text-body-sm font-medium tabular text-primary">{code}</p>
          ) : null}
          <h1 className="mt-2 text-h2 font-semibold tracking-tight text-text">{title}</h1>
          <p className="mt-3 text-body text-text-muted">{description}</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">{children}</div>
        </div>
      </main>
    </div>
  );
}

function HomeButton() {
  return (
    <Button asChild>
      <Link to="/">
        <Home aria-hidden="true" />
        Go to the homepage
      </Link>
    </Button>
  );
}

export function NotFoundPage() {
  return (
    <StandalonePage
      code="404"
      title="This page doesn’t exist"
      description="The link may be old or mistyped. Everything else is where you left it."
    >
      <HomeButton />
      <Button asChild variant="outline">
        <Link to="/projects">Browse projects</Link>
      </Button>
    </StandalonePage>
  );
}

export function ForbiddenPage() {
  return (
    <StandalonePage
      code="403"
      title="This area isn’t for your account"
      description="Sign in with a different account, or go back to your home page."
    >
      <HomeButton />
    </StandalonePage>
  );
}

export function MaintenancePage() {
  return (
    <StandalonePage
      title="DevSync is being updated"
      description="We’re applying an update and will be back in a few minutes. Your work is saved."
    >
      <Button
        variant="outline"
        onClick={() => {
          window.location.reload();
        }}
      >
        Check again
      </Button>
    </StandalonePage>
  );
}

export function ServerErrorPage({ requestId }: { requestId?: string | null }) {
  return (
    <StandalonePage
      code="500"
      title="Something went wrong on our side"
      description="Reload the page to try again. If it keeps happening, share the request ID with support."
    >
      <Button
        onClick={() => {
          window.location.reload();
        }}
      >
        Reload the page
      </Button>
      <Button asChild variant="outline">
        <Link to="/">Go to the homepage</Link>
      </Button>
      {requestId ? (
        <p className="w-full text-caption text-text-muted">
          Request ID <span className="font-mono">{requestId}</span>
        </p>
      ) : null}
    </StandalonePage>
  );
}

function isChunkError(error: unknown): boolean {
  return (
    error instanceof Error &&
    /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(
      error.message,
    )
  );
}

/** Route error boundary: 404s from the router stay 404; anything else is reported once. */
export function RouteError() {
  const error = useRouteError();
  const notFound = isRouteErrorResponse(error) && error.status === 404;
  useEffect(() => {
    if (!notFound) void reportClientError(error, isChunkError(error) ? "chunk" : "render");
  }, [error, notFound]);
  if (notFound) return <NotFoundPage />;
  if (isChunkError(error)) {
    return (
      <StandalonePage
        title="DevSync was updated"
        description="A newer version is available. Reload to continue where you were."
      >
        <Button
          onClick={() => {
            window.location.reload();
          }}
        >
          Reload the page
        </Button>
      </StandalonePage>
    );
  }
  return <ServerErrorPage requestId={error instanceof ApiError ? error.requestId : null} />;
}

/** In-shell placeholder for pages that later phases build (never a 404 for a menu link). */
export function ComingSoonPage({ title, phase }: { title: string; phase: number }) {
  return (
    <>
      <PageHeader title={title} description="This part of DevSync is on its way." />
      <Card>
        <EmptyState
          art={<NodeArt />}
          icon={<Construction aria-hidden="true" />}
          title={`${title} arrives in Phase ${String(phase)}`}
          description="It’s planned and listed in the menu so you can find it. Everything that’s ready works today."
        />
      </Card>
    </>
  );
}
