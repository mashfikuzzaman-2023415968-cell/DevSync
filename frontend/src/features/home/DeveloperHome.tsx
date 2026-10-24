import { Search } from "lucide-react";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import type { Bid, RecommendedProject } from "@/api/types";
import { NodeArt } from "@/components/brand/NodeArt";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardHeader, NewcomerBadge, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState, PageHeader, StatCard } from "@/components/ui/Feedback";
import { useMe } from "@/features/auth/api";
import { useMyBids } from "@/features/bids/api";
import { BID_STATUS_TONE, bidStatusLabel } from "@/features/bids/bidText";
import { useRecommended } from "@/features/marketplace/api";
import { useDeveloper, usePortfolio, useSkillTests } from "@/features/profile/api";
import { formatDays, formatMoney, formatScore } from "@/lib/format";
import { Checklist } from "./Checklist";
import { firstName, greeting } from "./greeting";

const RECOMMENDED_LIMIT = 6;
const RECENT_BIDS = 5;

/** Developer dashboard (spec §13.5 #9): open bids, competency and performance (or "Building
 * your record"), recommended projects, recent bids and the newcomer checklist. Invitations,
 * active projects and earnings join in later phases. */
export default function DeveloperHome() {
  const me = useMe();
  const user = me.data;
  const portfolio = usePortfolio();
  const tests = useSkillTests();
  const bids = useMyBids();
  const profile = useDeveloper(user?.id ?? "", true);
  const reputation = profile.data?.reputation ?? null;
  const hasPortfolio = (portfolio.data?.length ?? 0) > 0;
  const passedTest = tests.data?.some((t) => t.last_score !== null) === true;
  // The checklist stays until the developer is known not to be a newcomer.
  const showChecklist = reputation?.is_newcomer !== false;
  return (
    <>
      <PageHeader
        title={`${greeting()}, ${firstName(user?.display_name)}`}
        description="Your bids, record and projects that fit your skills."
        action={
          <Button asChild>
            <Link to="/dev/find">
              <Search aria-hidden="true" />
              Find projects
            </Link>
          </Button>
        }
      />
      <section aria-label="Your numbers" className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-3">
        <div className="col-span-2 lg:col-span-1">
          {bids.isPending ? (
            <Skeleton className="h-28 rounded-lg" />
          ) : bids.isError ? (
            <Card className="p-5">
              <p className="text-body-sm text-text-muted">Open bids</p>
              <p className="mt-2 text-body-sm text-text">Couldn’t load your bids.</p>
            </Card>
          ) : (
            <StatCard
              label="Open bids"
              value={bids.data.filter((b) => b.status === "ACTIVE").length}
            />
          )}
        </div>
        {profile.isPending ? (
          <>
            <Skeleton className="h-28 rounded-lg" />
            <Skeleton className="h-28 rounded-lg" />
          </>
        ) : reputation && reputation.competency !== null && reputation.performance !== null ? (
          <>
            <StatCard
              label="Competency"
              value={Number(reputation.competency) * 100}
              format={(v) => formatScore(v / 100)}
              hint={reputation.seeded ? "Seeded for the demo" : "Out of 100"}
            />
            <StatCard
              label="Performance"
              value={Number(reputation.performance) * 100}
              format={(v) => formatScore(v / 100)}
              hint={reputation.seeded ? "Seeded for the demo" : "Out of 100"}
            />
          </>
        ) : (
          <Card className="col-span-2 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-body-sm text-text-muted">Competency and performance</p>
              {reputation?.is_newcomer ? <NewcomerBadge /> : null}
            </div>
            <p className="mt-2 text-h4 font-semibold text-text">
              {profile.isError ? "Couldn’t load your record" : "Building your record"}
            </p>
            {profile.isError ? (
              <Button variant="outline" className="mt-3" onClick={() => void profile.refetch()}>
                Try again
              </Button>
            ) : (
              <p className="mt-1 text-caption text-text-muted">
                Your scores appear after your first completed project.
              </p>
            )}
          </Card>
        )}
      </section>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <div className="min-w-0 space-y-6">
          <Recommended />
          <RecentBids query={bids} />
          <Card>
            <EmptyState
              art={<NodeArt />}
              title="No active projects yet"
              description="When a client picks you for a team, the project, your tasks and the next deadline appear here."
              action={
                <Button asChild variant="outline">
                  <Link to="/dev/find">Browse open projects</Link>
                </Button>
              }
            />
          </Card>
        </div>
        {showChecklist ? (
          <Card className="h-fit">
            <CardHeader
              title="Get ready for your first team"
              description="Newcomers get a fair first chance; these steps help clients pick you."
              action={<NewcomerBadge />}
            />
            <div className="mt-2">
              <Checklist
                items={[
                  {
                    label: "Verify your phone",
                    done: user?.phone_verified === true,
                    hint: "Proves you’re a real person; one account per number.",
                    to: "/verify",
                  },
                  {
                    label: "Verify your email",
                    done: user?.email_verified === true,
                    hint: "We send invitations and payment notices there.",
                    to: "/verify",
                  },
                  {
                    label: "Add a portfolio item",
                    done: hasPortfolio,
                    hint: "Show one piece of real work, with a screenshot if you can.",
                    to: "/dev/profile",
                  },
                  {
                    label: "Take a skill test",
                    done: passedTest,
                    hint: "A good score lets you be considered before you have reviews.",
                    to: "/dev/challenges",
                  },
                ]}
              />
            </div>
          </Card>
        ) : null}
      </div>
    </>
  );
}

function Recommended() {
  const recommended = useRecommended();
  return (
    <Card>
      <CardHeader
        title="Recommended for you"
        description="Open projects needing your skills, with deadlines that fit your pace."
      />
      {recommended.isPending ? (
        <div aria-hidden="true" className="flex gap-4 p-5">
          <Skeleton className="h-36 flex-1 rounded-md" />
          <Skeleton className="hidden h-36 flex-1 rounded-md sm:block" />
        </div>
      ) : recommended.isError ? (
        <ErrorState
          title="Recommendations didn’t load"
          requestId={recommended.error instanceof ApiError ? recommended.error.requestId : null}
          onRetry={() => void recommended.refetch()}
        />
      ) : recommended.data.length === 0 ? (
        <EmptyState
          icon={<Search />}
          title="No matches right now"
          description="Add skills to your profile and we’ll suggest open projects that need them."
          action={
            <Button asChild variant="outline">
              <Link to="/dev/profile">Add skills</Link>
            </Button>
          }
        />
      ) : (
        <ul className="mx-5 mb-5 mt-4 flex snap-x snap-mandatory gap-4 overflow-x-auto pb-2 sm:grid sm:snap-none sm:grid-cols-2 sm:overflow-visible sm:pb-0 2xl:grid-cols-3">
          {recommended.data.slice(0, RECOMMENDED_LIMIT).map((r) => (
            <RecommendedItem key={r.project.id} item={r} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function RecommendedItem({ item }: { item: RecommendedProject }) {
  const p = item.project;
  return (
    <li className="w-64 shrink-0 snap-start sm:w-auto">
      <Link
        to={`/dev/projects/${p.id}`}
        className="flex h-full flex-col rounded-md border border-border p-4 transition-colors duration-fast ease-standard hover:border-primary/40 hover:bg-surface-2"
      >
        <span className="line-clamp-2 font-medium text-text">{p.title}</span>
        <span className="mt-1 text-body-sm text-text-muted">
          {formatMoney(p.budget_paisa)} budget, {formatDays(p.deadline_days)} to deliver
        </span>
        {item.matched_skills.length > 0 ? (
          <span className="mt-3 flex flex-wrap gap-1.5">
            {item.matched_skills.map((s) => (
              <Badge key={s} tone="primary" icon={false}>
                {s}
              </Badge>
            ))}
          </span>
        ) : null}
      </Link>
    </li>
  );
}

function RecentBids({ query }: { query: ReturnType<typeof useMyBids> }) {
  const latest: Bid[] = [...(query.data ?? [])]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, RECENT_BIDS);
  return (
    <Card>
      <CardHeader
        title="Recent bids"
        description="Your latest sealed bids and where they stand."
        action={
          <Button asChild variant="ghost">
            <Link to="/dev/bids">All bids</Link>
          </Button>
        }
      />
      {query.isPending ? (
        <div aria-hidden="true" className="space-y-3 p-5">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : query.isError ? (
        <ErrorState
          title="Your bids didn’t load"
          requestId={query.error instanceof ApiError ? query.error.requestId : null}
          onRetry={() => void query.refetch()}
        />
      ) : latest.length === 0 ? (
        <EmptyState
          title="No bids yet"
          description="Find a project that fits your skills and place a sealed bid."
          action={
            <Button asChild variant="outline">
              <Link to="/dev/find">Find projects</Link>
            </Button>
          }
        />
      ) : (
        <ul className="mt-3 divide-y divide-border border-t border-border">
          {latest.map((b) => (
            <li key={b.id} className="flex items-center justify-between gap-3 px-5 py-3">
              <div className="min-w-0">
                <Link
                  to={`/dev/projects/${b.project_id}`}
                  className="inline-flex min-h-11 max-w-full items-center font-medium text-text hover:text-primary hover:underline"
                >
                  <span className="truncate">{b.project_title}</span>
                </Link>
                <p className="text-body-sm text-text-muted">{b.slot_label}</p>
              </div>
              <Badge tone={BID_STATUS_TONE[b.status] ?? "neutral"}>
                {bidStatusLabel(b.status)}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
