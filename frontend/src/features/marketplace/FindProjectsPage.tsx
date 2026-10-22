/**
 * Find Projects (spec §13.5 #10): search and filter open projects, with the filters kept in the
 * URL so a reload or the Back button restores them. No bid data is shown (sealed, §14.5). A
 * recommended strip (§9.16) sits above the results.
 */
import { Link, useSearchParams } from "react-router";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useSkills } from "@/features/profile/api";
import { TagPicker } from "@/features/projects/TagPicker";
import { formatDays, formatMoney } from "@/lib/format";
import type { ProjectCard as Card_ } from "@/api/types";
import { useProjectSearch, useRecommended, type SearchFilters } from "./api";

type Sort = "newest" | "budget" | "deadline";

function filtersFromParams(p: URLSearchParams): SearchFilters {
  const skills = p.getAll("skills");
  const num = (k: string) => (p.get(k) ? Number(p.get(k)) : undefined);
  return {
    q: p.get("q") ?? "",
    skills,
    budget_min: num("budget_min"),
    deadline_max: num("deadline_max"),
    team_size: num("team_size"),
    sort: p.get("sort") ?? "newest",
  };
}

export default function FindProjectsPage() {
  const [params, setParams] = useSearchParams();
  const filters = filtersFromParams(params);
  const search = useProjectSearch(filters);
  const recommended = useRecommended();
  const skills = useSkills();

  function patch(next: Partial<Record<string, string | string[] | undefined>>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      p.delete(k);
      if (Array.isArray(v)) for (const item of v) p.append(k, item);
      else if (v) p.set(k, v);
    }
    setParams(p, { replace: true });
  }

  const items = search.data?.pages.flatMap((pg) => pg.items) ?? [];
  const skillOptions = (skills.data ?? []).map((s) => ({ value: s.name, label: s.name }));

  return (
    <>
      <PageHeader
        title="Find work"
        description="Search open projects and place a sealed bid. Only the client sees your bid."
      />

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,9fr)]">
        <Card className="h-fit">
          <CardHeader title="Filters" />
          <div className="mt-4 flex flex-col gap-4">
            <Field
              label="Search projects"
              type="search"
              value={filters.q ?? ""}
              onChange={(e) => {
                patch({ q: e.target.value });
              }}
              placeholder="e.g. ordering system"
              enterKeyHint="search"
            />
            <div>
              <p className="mb-1.5 text-body-sm font-medium text-text">Skills</p>
              <TagPicker
                options={skillOptions}
                value={filters.skills ?? []}
                onChange={(v) => {
                  patch({ skills: v });
                }}
                empty="Loading skills…"
              />
            </div>
            <Field
              label="Max deadline (days)"
              type="number"
              inputMode="numeric"
              min={1}
              max={365}
              value={filters.deadline_max ?? ""}
              onChange={(e) => {
                patch({ deadline_max: e.target.value || undefined });
              }}
            />
            <div>
              <p className="mb-1.5 text-body-sm font-medium text-text">Sort</p>
              <SegmentedControl<Sort>
                label="Sort projects"
                size="sm"
                value={(filters.sort ?? "newest") as Sort}
                onChange={(v) => {
                  patch({ sort: v });
                }}
                segments={[
                  { value: "newest", label: "Newest" },
                  { value: "budget", label: "Budget" },
                  { value: "deadline", label: "Deadline" },
                ]}
              />
            </div>
          </div>
        </Card>

        <div className="flex flex-col gap-6">
          {recommended.data && recommended.data.length > 0 ? (
            <Card>
              <CardHeader
                title="Recommended for you"
                description="Open projects needing your skills, with deadlines that fit your usual pace and hours you have free."
              />
              <ul className="mt-3 flex flex-wrap gap-2">
                {recommended.data.slice(0, 6).map((r) => (
                  <li key={r.project.id}>
                    <Button asChild variant="outline">
                      <Link to={`/dev/projects/${r.project.id}`}>
                        {r.project.title}
                        <span className="text-text-muted">
                          {r.matched_skills.length > 0
                            ? `Needs ${r.matched_skills.join(", ")}`
                            : r.skill_match_count === 1
                              ? "1 matching skill"
                              : `${String(r.skill_match_count)} matching skills`}
                        </span>
                      </Link>
                    </Button>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}

          {search.isLoading ? (
            <Card>
              <Skeleton className="h-40 w-full" />
            </Card>
          ) : search.isError ? (
            <Card>
              <ErrorState onRetry={() => void search.refetch()} />
            </Card>
          ) : items.length === 0 ? (
            <Card>
              <EmptyState
                title="No projects match"
                description="Try fewer filters or a different search."
              />
            </Card>
          ) : (
            <>
              <ul className="flex flex-col gap-4">
                {items.map((p) => (
                  <li key={p.id}>
                    <ProjectResult project={p} />
                  </li>
                ))}
              </ul>
              {search.hasNextPage ? (
                <Button
                  variant="outline"
                  loading={search.isFetchingNextPage}
                  onClick={() => void search.fetchNextPage()}
                >
                  Load more
                </Button>
              ) : null}
            </>
          )}
        </div>
      </div>
    </>
  );
}

function ProjectResult({ project }: { project: Card_ }) {
  return (
    <Card interactive className="transition-shadow">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <Link
            to={`/dev/projects/${project.id}`}
            className="inline-flex min-h-11 items-center font-medium text-text hover:text-primary hover:underline"
          >
            {project.title}
          </Link>
          <p className="mt-1 line-clamp-2 text-body-sm text-text-muted">{project.summary}</p>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {project.skills.map((s) => (
              <li key={s}>
                <Badge tone="neutral">{s}</Badge>
              </li>
            ))}
          </ul>
        </div>
        <div className="shrink-0 text-right">
          <p className="font-semibold tabular text-text">{formatMoney(project.budget_paisa)}</p>
          <p className="text-body-sm text-text-muted">{formatDays(project.deadline_days)}</p>
          <p className="text-caption text-text-subtle">{project.team_size} people</p>
        </div>
      </div>
    </Card>
  );
}
