/**
 * Find Projects (spec §13.5 #10): search and filter open projects, with every filter kept in
 * the URL so a reload or the Back button restores them. Filters: text, skills, budget range
 * (taka in the URL, paisa to the API), max deadline, role (a slot skill), team size and the hours
 * a week you can commit (the server keeps projects whose period fits them next to your confirmed
 * reservations, §9.17). Cards highlight the skills on your profile. No bid data is shown
 * (sealed, §14.5). A recommended strip (§9.16) sits above the results.
 */
import { SearchX } from "lucide-react";
import { Link, useSearchParams } from "react-router";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { Field, FormField } from "@/components/ui/Field";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { useDeveloperProfile, useSkills } from "@/features/profile/api";
import { TagPicker } from "@/features/projects/TagPicker";
import { formatDays, formatMoney } from "@/lib/format";
import type { ProjectCard as Card_ } from "@/api/types";
import { useProjectSearch, useRecommended } from "./api";
import { FILTER_KEYS, parseFilters } from "./filters";

type Sort = "newest" | "budget" | "deadline";
const ANY = "any";
const TEAM_SIZES = [2, 3, 4, 5, 6, 7, 8, 9, 10];

export default function FindProjectsPage() {
  const [params, setParams] = useSearchParams();
  const { api: filters, errors, active } = parseFilters(params);
  const search = useProjectSearch(filters);
  const recommended = useRecommended();
  const skills = useSkills();
  const profile = useDeveloperProfile();
  const mine = new Set((profile.data?.skills ?? []).map((s) => s.name.toLowerCase()));

  function patch(next: Partial<Record<string, string | string[] | undefined>>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      p.delete(k);
      if (Array.isArray(v)) for (const item of v) p.append(k, item);
      else if (v) p.set(k, v);
    }
    setParams(p, { replace: true });
  }

  function clearFilters() {
    const p = new URLSearchParams(params);
    for (const k of FILTER_KEYS) p.delete(k);
    setParams(p, { replace: true });
  }

  const items = search.data?.pages.flatMap((pg) => pg.items) ?? [];
  const skillNames = (skills.data ?? []).map((s) => s.name);
  const skillOptions = skillNames.map((name) => ({ value: name, label: name }));
  const role = params.get("role") ?? "";
  const roleOptions = [
    { value: ANY, label: "Any role" },
    ...(role && !skillNames.includes(role) ? [{ value: role, label: role }] : []),
    ...skillOptions,
  ];
  const raw = (k: string) => params.get(k) ?? "";

  return (
    <>
      <PageHeader
        title="Find work"
        description="Search open projects and place a sealed bid. Only the client sees your bid."
      />

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,9fr)]">
        <Card className="h-fit">
          <CardHeader
            title="Filters"
            action={
              active ? (
                <Button variant="ghost" size="sm" onClick={clearFilters}>
                  Clear filters
                </Button>
              ) : undefined
            }
          />
          <div className="mt-4 flex flex-col gap-4 px-5 pb-5">
            <Field
              label="Search projects"
              type="search"
              value={raw("q")}
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
            {/* Side by side, except in the narrow filter column of mid-size laptops. */}
            <fieldset className="grid grid-cols-2 gap-3 lg:grid-cols-1 2xl:grid-cols-2">
              <legend className="mb-1.5 text-body-sm font-medium text-text">Budget (৳)</legend>
              <Field
                label="Minimum"
                type="number"
                inputMode="numeric"
                min={0}
                step={1}
                value={raw("budget_min")}
                error={errors.budget_min}
                onChange={(e) => {
                  patch({ budget_min: e.target.value || undefined });
                }}
              />
              <Field
                label="Maximum"
                type="number"
                inputMode="numeric"
                min={0}
                step={1}
                value={raw("budget_max")}
                error={errors.budget_max}
                onChange={(e) => {
                  patch({ budget_max: e.target.value || undefined });
                }}
              />
            </fieldset>
            <Field
              label="Max deadline (days)"
              type="number"
              inputMode="numeric"
              min={1}
              max={365}
              value={raw("deadline_max")}
              error={errors.deadline_max}
              onChange={(e) => {
                patch({ deadline_max: e.target.value || undefined });
              }}
            />
            <FormField label="Role" hint="Projects with a slot needing this skill.">
              {(a11y) => (
                <Select
                  {...a11y}
                  value={role || ANY}
                  onChange={(v) => {
                    patch({ role: v === ANY ? undefined : v });
                  }}
                  options={roleOptions}
                />
              )}
            </FormField>
            <FormField label="Team size" error={errors.team_size}>
              {(a11y) => (
                <Select
                  {...a11y}
                  value={filters.team_size ? String(filters.team_size) : ANY}
                  onChange={(v) => {
                    patch({ team_size: v === ANY ? undefined : v });
                  }}
                  options={[
                    { value: ANY, label: "Any size" },
                    ...TEAM_SIZES.map((n) => ({ value: String(n), label: `${String(n)} people` })),
                  ]}
                />
              )}
            </FormField>
            <Field
              label="Hours a week you can give"
              type="number"
              inputMode="numeric"
              min={1}
              max={168}
              hint="Shows projects that fit next to the work you’ve already committed to."
              value={raw("hours")}
              error={errors.hours}
              onChange={(e) => {
                patch({ hours: e.target.value || undefined });
              }}
            />
            <div>
              <p className="mb-1.5 text-body-sm font-medium text-text">Sort</p>
              <SegmentedControl<Sort>
                label="Sort projects"
                size="sm"
                // Fill the narrow filter column instead of poking out of its card.
                className="flex w-full [&>button]:px-2"
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
              <ul className="flex flex-wrap gap-2 p-5 pt-3">
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
            <Card aria-busy="true" aria-label="Loading projects">
              <div className="flex flex-col gap-3 p-5">
                <Skeleton className="h-5 w-1/2" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-6 w-1/3" />
              </div>
            </Card>
          ) : search.isError ? (
            <Card>
              <ErrorState onRetry={() => void search.refetch()} />
            </Card>
          ) : items.length === 0 ? (
            <Card>
              <EmptyState
                icon={<SearchX />}
                title="No projects match"
                description={
                  search.hasNextPage
                    ? "None of the projects checked so far fit. Search further, or broaden your filters."
                    : active
                      ? "Try fewer skills, a wider budget or deadline, any role or team size, or more hours a week."
                      : "No open projects right now. New ones appear here as clients publish them."
                }
                action={
                  search.hasNextPage ? (
                    <Button
                      loading={search.isFetchingNextPage}
                      onClick={() => void search.fetchNextPage()}
                    >
                      Search further
                    </Button>
                  ) : active ? (
                    <Button variant="outline" onClick={clearFilters}>
                      Clear filters
                    </Button>
                  ) : undefined
                }
              />
            </Card>
          ) : (
            <>
              <ul className="flex flex-col gap-4">
                {items.map((p) => (
                  <li key={p.id}>
                    <ProjectResult project={p} mine={mine} />
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

function ProjectResult({ project, mine }: { project: Card_; mine: Set<string> }) {
  // Your skills first, so the match is visible at a glance.
  const skills = [...project.skills].sort(
    (a, b) => Number(mine.has(b.toLowerCase())) - Number(mine.has(a.toLowerCase())),
  );
  const matches = skills.filter((s) => mine.has(s.toLowerCase())).length;
  return (
    <Card interactive className="p-5 transition-shadow">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <Link
            to={`/dev/projects/${project.id}`}
            className="inline-flex min-h-11 items-center font-medium text-text hover:text-primary hover:underline"
          >
            {project.title}
          </Link>
          <p className="mt-1 line-clamp-2 text-body-sm text-text-muted">{project.summary}</p>
          <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Skills needed">
            {skills.map((s) => {
              const yours = mine.has(s.toLowerCase());
              return (
                <li key={s}>
                  <Badge tone={yours ? "primary" : "neutral"} icon={yours}>
                    {s}
                    {yours ? <span className="sr-only"> (your skill)</span> : null}
                  </Badge>
                </li>
              );
            })}
          </ul>
          {matches > 0 ? (
            <p className="mt-2 text-caption text-text-muted">
              {matches === 1 ? "1 of your skills" : `${String(matches)} of your skills`}
            </p>
          ) : null}
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
