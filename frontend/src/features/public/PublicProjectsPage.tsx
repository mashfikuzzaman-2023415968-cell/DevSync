/** Public project list (spec §13.5 #6): projects open for bids, for anyone, with search. Cards
 * show only public columns (no client identity, never any bid data); each opens `/p/:id`. */
import { Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import type { ProjectCard } from "@/api/types";
import { Still } from "@/components/brand/Still";
import { Button } from "@/components/ui/Button";
import { Badge, Card, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { SiteFooter } from "@/features/landing/SiteFooter";
import { SiteHeader } from "@/features/landing/SiteHeader";
import { usePublicProjects } from "@/features/marketplace/api";
import { formatDate, formatDays, formatMoney } from "@/lib/format";

export default function PublicProjectsPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [text, setText] = useState(q);
  const list = usePublicProjects(q);
  const projects = list.data?.pages.flatMap((page) => page.items) ?? [];

  function submit(e: FormEvent) {
    e.preventDefault();
    const next = text.trim();
    setParams(next ? { q: next } : {}, { replace: true });
  }

  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <SiteHeader />
      <main id="main" className="mx-auto w-full max-w-content flex-1 px-4 pb-20 pt-28 sm:px-6">
        <h1 className="text-h1 font-semibold tracking-tight text-text">Browse projects</h1>
        <p className="mt-2 max-w-2xl text-lead text-text-muted">
          Software projects looking for a team, with the budget, team size, skills and deadline of
          each.
        </p>

        <form role="search" onSubmit={submit} className="mt-8 flex max-w-xl items-end gap-3">
          <Field
            label="Search projects"
            type="search"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
            }}
            placeholder="e.g. React, ordering, mobile"
            className="flex-1"
          />
          <Button type="submit" variant="outline">
            <Search aria-hidden="true" />
            Search
          </Button>
        </form>

        <div className="mt-8">
          {list.isPending ? (
            <div
              className="grid gap-4 md:grid-cols-2"
              aria-busy="true"
              aria-label="Loading projects"
            >
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-40 w-full rounded-lg" />
              ))}
            </div>
          ) : list.isError ? (
            <Card>
              <ErrorState
                title="We couldn’t load the projects"
                requestId={list.error instanceof ApiError ? list.error.requestId : null}
                onRetry={() => void list.refetch()}
              />
            </Card>
          ) : projects.length === 0 ? (
            <Card>
              {q ? (
                <EmptyState
                  title={`No open projects match “${q}”`}
                  description="Try a skill or a shorter word, or clear the search to see every open project."
                  action={
                    <Button
                      variant="outline"
                      onClick={() => {
                        setText("");
                        setParams({}, { replace: true });
                      }}
                    >
                      Clear the search
                    </Button>
                  }
                />
              ) : (
                <EmptyState
                  art={<Still name="team" className="w-60" />}
                  title="No projects are open for bids right now"
                  description="When clients publish projects they’ll be listed here. Create a developer account now so you’re ready to bid."
                  action={<JoinButtons />}
                />
              )}
            </Card>
          ) : (
            <>
              <ul className="grid gap-4 md:grid-cols-2">
                {projects.map((p) => (
                  <li key={p.id}>
                    <ProjectTile project={p} />
                  </li>
                ))}
              </ul>
              {list.hasNextPage ? (
                <div className="mt-6 flex justify-center">
                  <Button
                    variant="outline"
                    loading={list.isFetchingNextPage}
                    onClick={() => void list.fetchNextPage()}
                  >
                    Load more
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}

function ProjectTile({ project: p }: { project: ProjectCard }) {
  return (
    <Card interactive className="flex h-full flex-col p-5">
      <Link
        to={`/p/${p.id}`}
        className="inline-flex min-h-11 items-center text-lead font-semibold text-text hover:text-primary hover:underline"
      >
        {p.title}
      </Link>
      {p.summary ? (
        <p className="mt-1 line-clamp-2 text-body-sm text-text-muted">{p.summary}</p>
      ) : null}
      {p.skills.length > 0 ? (
        <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Skills needed">
          {p.skills.map((s) => (
            <li key={s}>
              <Badge tone="neutral">{s}</Badge>
            </li>
          ))}
        </ul>
      ) : null}
      <dl className="mt-auto grid grid-cols-3 gap-3 pt-4 text-body-sm">
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
      </dl>
      {p.bidding_deadline ? (
        <p className="mt-3 text-caption text-text-muted">
          Bids close {formatDate(p.bidding_deadline)}
        </p>
      ) : null}
    </Card>
  );
}

export function JoinButtons() {
  return (
    <div className="flex flex-col gap-3 sm:flex-row">
      <Button asChild>
        <Link to="/register?role=developer">Create a developer account</Link>
      </Button>
      <Button asChild variant="outline">
        <Link to="/register?role=client">Post a project</Link>
      </Button>
    </div>
  );
}
