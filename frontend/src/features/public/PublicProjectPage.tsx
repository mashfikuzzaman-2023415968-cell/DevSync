/** Public view of one project (spec §13.5 #6 `/p/:id`): what a visitor needs to decide whether
 * to bid — summary, requirements, budget, deadline, team and roles — and a way in. Public
 * columns only; signing in returns to the bid sheet. */
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { Alert, EmptyState, ErrorState } from "@/components/ui/Feedback";
import { SiteFooter } from "@/features/landing/SiteFooter";
import { SiteHeader } from "@/features/landing/SiteHeader";
import { useMe } from "@/features/auth/api";
import { usePublicProject } from "@/features/marketplace/api";
import { formatDate, formatDays, formatMoney } from "@/lib/format";

export default function PublicProjectPage() {
  const { id = "" } = useParams();
  const project = usePublicProject(id);
  const me = useMe();
  const bidPath = `/dev/projects/${id}`;

  let body;
  if (project.isPending) {
    body = (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading the project">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-48 w-full rounded-lg" />
      </div>
    );
  } else if (project.isError) {
    const err = project.error;
    body =
      err instanceof ApiError && err.status === 404 ? (
        <Card>
          <EmptyState
            title="This project isn’t open to view"
            description="It may have been taken down, or it was never published."
            action={
              <Button asChild variant="outline">
                <Link to="/projects">See open projects</Link>
              </Button>
            }
          />
        </Card>
      ) : (
        <Card>
          <ErrorState
            title="We couldn’t load this project"
            requestId={err instanceof ApiError ? err.requestId : null}
            onRetry={() => void project.refetch()}
          />
        </Card>
      );
  } else {
    const p = project.data;
    const signedInDeveloper = me.data?.role === "DEVELOPER";
    body = (
      <>
        <h1 className="text-h1 font-semibold tracking-tight text-text">{p.title}</h1>
        {p.summary ? <p className="mt-2 max-w-3xl text-lead text-text-muted">{p.summary}</p> : null}

        <div className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
          <Card>
            <CardHeader title="What the client needs" />
            <div className="p-5">
              {p.requirements ? (
                <p className="whitespace-pre-wrap text-body text-text">{p.requirements}</p>
              ) : (
                <p className="text-body-sm text-text-muted">
                  The client hasn’t written requirements beyond the summary.
                </p>
              )}
              <h2 className="mt-6 text-body-sm font-semibold text-text">Roles</h2>
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {p.slots.map((s) => (
                  <li key={s.id}>
                    <Badge tone="neutral">
                      {s.label ? `${s.skill}: ${s.label}` : s.skill} ×{s.count}
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>
          </Card>

          <Card>
            <CardHeader title="At a glance" />
            <div className="p-5">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-body-sm">
                <div>
                  <dt className="text-text-muted">Budget</dt>
                  <dd className="font-semibold tabular text-text">{formatMoney(p.budget_paisa)}</dd>
                </div>
                <div>
                  <dt className="text-text-muted">Deadline</dt>
                  <dd className="font-medium text-text">{formatDays(p.deadline_days)}</dd>
                </div>
                <div>
                  <dt className="text-text-muted">Team</dt>
                  <dd className="font-medium text-text">{p.team_size} people</dd>
                </div>
                {p.bidding_deadline ? (
                  <div>
                    <dt className="text-text-muted">Bids close</dt>
                    <dd className="font-medium text-text">{formatDate(p.bidding_deadline)}</dd>
                  </div>
                ) : null}
              </dl>
              {p.open_for_bids ? (
                <div className="mt-6 flex flex-col gap-3">
                  {signedInDeveloper ? (
                    <Button asChild>
                      <Link to={bidPath}>Place a sealed bid</Link>
                    </Button>
                  ) : (
                    <>
                      <Button asChild>
                        <Link to={`/login?return_to=${encodeURIComponent(bidPath)}`}>
                          Sign in to bid
                        </Link>
                      </Button>
                      <Button asChild variant="outline">
                        <Link to="/register?role=developer">Create a developer account</Link>
                      </Button>
                    </>
                  )}
                  <p className="text-caption text-text-muted">
                    Bids are sealed: only the client sees your price.
                  </p>
                </div>
              ) : (
                <Alert tone="info" title="Bidding has closed" className="mt-6">
                  This project isn’t taking bids any more.
                </Alert>
              )}
            </div>
          </Card>
        </div>
      </>
    );
  }

  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <SiteHeader />
      <main id="main" className="mx-auto w-full max-w-content flex-1 px-4 pb-20 pt-28 sm:px-6">
        <Link
          to="/projects"
          className="mb-6 inline-flex min-h-11 items-center gap-1.5 text-body-sm font-medium text-primary hover:underline"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          All open projects
        </Link>
        {body}
      </main>
      <SiteFooter />
    </div>
  );
}
