/** Public developer profile (spec §13.5 #7): what a client or visitor sees. Never email or
 * phone; a clients-only profile is "not found" for everyone else. */
import { BadgeCheck, CalendarDays, Clock, ExternalLink, GitBranch, ImageOff } from "lucide-react";
import { Link, useParams } from "react-router";
import { ApiError, fileUrl } from "@/api/client";
import type { PublicProfile } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Avatar, Badge, Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { EmptyState, ErrorState, RingProgress } from "@/components/ui/Feedback";
import { useMe } from "@/features/auth/api";
import { SiteFooter } from "@/features/landing/SiteFooter";
import { SiteHeader } from "@/features/landing/SiteHeader";
import { formatDate, formatScore } from "@/lib/format";
import { useDeveloper } from "./api";

const LEVEL_WORDS = ["", "Learning", "Basic", "Comfortable", "Strong", "Expert"];

function Profile({ p, isMe }: { p: PublicProfile; isMe: boolean }) {
  const names = new Map(p.skills.map((s) => [s.skill_id, s.name]));
  return (
    <>
      <section className="flex flex-col gap-6 sm:flex-row sm:items-center">
        <Avatar name={p.display_name} size="lg" />
        <div className="min-w-0 flex-1">
          <h1 className="text-h2 font-semibold tracking-tight text-text">{p.display_name}</h1>
          {p.headline ? <p className="mt-1 text-lead text-text-muted">{p.headline}</p> : null}
          <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-body-sm text-text-muted">
            <li className="inline-flex items-center gap-1.5">
              <Clock className="size-4" aria-hidden="true" />
              {p.hours_per_week} hours a week
            </li>
            <li className="inline-flex items-center gap-1.5">
              <CalendarDays className="size-4" aria-hidden="true" />
              On DevSync since {formatDate(p.member_since)}
            </li>
            {p.github_username ? (
              <li>
                <a
                  href={`https://github.com/${encodeURIComponent(p.github_username)}`}
                  rel="noopener noreferrer nofollow"
                  className="inline-flex items-center gap-1.5 text-primary underline-offset-4 hover:underline"
                >
                  <GitBranch className="size-4" aria-hidden="true" />
                  {p.github_username}
                </a>
              </li>
            ) : null}
          </ul>
        </div>
        {isMe ? (
          <Button asChild variant="outline">
            <Link to="/dev/profile">Edit profile</Link>
          </Button>
        ) : null}
      </section>

      <div className="mt-10 grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <div className="space-y-6">
          {p.bio ? (
            <Card className="p-5">
              <h2 className="text-body font-semibold text-text">About</h2>
              <p className="mt-2 whitespace-pre-line text-body text-text">{p.bio}</p>
            </Card>
          ) : null}
          <section aria-labelledby="work-title">
            <h2 id="work-title" className="mb-3 text-h4 font-semibold text-text">
              Work
            </h2>
            {p.portfolio.length === 0 ? (
              <Card>
                <EmptyState
                  icon={<ImageOff />}
                  title="No portfolio items yet"
                  description="Work this developer adds shows up here."
                />
              </Card>
            ) : (
              <ul className="grid gap-6 sm:grid-cols-2">
                {p.portfolio.map((item) => (
                  <li key={item.id}>
                    <Card className="h-full overflow-hidden">
                      {item.image_ids[0] ? (
                        <img
                          src={fileUrl(item.image_ids[0])}
                          alt={`${item.title}, screenshot`}
                          loading="lazy"
                          className="aspect-[16/10] w-full border-b border-border object-cover"
                        />
                      ) : null}
                      <div className="p-5">
                        <h3 className="text-body font-semibold text-text">{item.title}</h3>
                        {item.description ? (
                          <p className="mt-1 line-clamp-4 text-body-sm text-text-muted">
                            {item.description}
                          </p>
                        ) : null}
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          {item.skill_ids.map((id) => (
                            <Badge key={id} tone="primary" icon={false}>
                              {names.get(id) ?? "Skill"}
                            </Badge>
                          ))}
                          {item.url ? (
                            <a
                              href={item.url}
                              rel="noopener noreferrer nofollow ugc"
                              className="inline-flex items-center gap-1 text-body-sm text-primary underline-offset-4 hover:underline"
                            >
                              <ExternalLink className="size-3.5" aria-hidden="true" />
                              Visit
                            </a>
                          ) : null}
                        </div>
                        {item.image_ids.length > 1 ? (
                          <ul className="mt-4 grid grid-cols-4 gap-2">
                            {item.image_ids.slice(1).map((id, i) => (
                              <li key={id}>
                                <img
                                  src={fileUrl(id)}
                                  alt={`${item.title}, screenshot ${String(i + 2)}`}
                                  loading="lazy"
                                  className="aspect-square w-full rounded-md border border-border object-cover"
                                />
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    </Card>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
        <aside className="space-y-6">
          <Card>
            <CardHeader title="Verified scores" description="From timed DevSync skill tests." />
            {p.verified_scores.length ? (
              <ul className="space-y-4 p-5">
                {p.verified_scores.map((v) => (
                  <li key={v.skill_id} className="flex items-center gap-4">
                    <RingProgress
                      value={Number(v.score) * 100}
                      size={52}
                      label={`${v.name} test score`}
                    >
                      {formatScore(Number(v.score))}
                    </RingProgress>
                    <div>
                      <p className="text-body-sm font-medium text-text">{v.name}</p>
                      <p className="text-caption text-text-muted">Tested {formatDate(v.at)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="p-5 text-body-sm text-text-muted">No tests taken yet.</p>
            )}
          </Card>
          <Card>
            <CardHeader title="Skills" description="As rated by the developer." />
            {p.skills.length ? (
              <ul className="divide-y divide-border">
                {p.skills.map((s) => (
                  <li
                    key={s.skill_id}
                    className="flex items-center justify-between gap-3 px-5 py-3 text-body-sm"
                  >
                    <span className="font-medium text-text">{s.name}</span>
                    <span className="text-text-muted">
                      {LEVEL_WORDS[s.self_level]} ({s.self_level} of 5)
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="p-5 text-body-sm text-text-muted">No skills listed yet.</p>
            )}
          </Card>
          {p.certificates.length ? (
            <Card>
              <CardHeader title="Certificates" description="Checked by a DevSync admin." />
              <ul className="space-y-3 p-5">
                {p.certificates.map((c) => (
                  <li
                    key={`${c.title}-${c.issuer}`}
                    className="flex items-start gap-2 text-body-sm"
                  >
                    <BadgeCheck
                      className="mt-0.5 size-4 shrink-0 text-success"
                      aria-hidden="true"
                    />
                    <span>
                      <span className="font-medium text-text">{c.title}</span>
                      <span className="block text-text-muted">{c.issuer}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </aside>
      </div>
    </>
  );
}

export default function PublicProfilePage() {
  const { id = "" } = useParams();
  const me = useMe();
  const signedIn = Boolean(me.data);
  const profile = useDeveloper(id, signedIn);
  const ready = !me.isPending;
  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <SiteHeader />
      <main id="main" className="mx-auto w-full max-w-content flex-1 px-4 pb-20 pt-28 sm:px-6">
        {!ready || profile.isPending ? (
          <div aria-hidden="true" className="space-y-6">
            <div className="flex items-center gap-6">
              <Skeleton className="size-20 rounded-full" />
              <div className="flex-1 space-y-3">
                <Skeleton className="h-8 w-64" />
                <Skeleton className="h-5 w-96 max-w-full" />
              </div>
            </div>
            <Skeleton className="h-64" />
          </div>
        ) : profile.isError ? (
          <Card>
            {profile.error instanceof ApiError && profile.error.status === 404 ? (
              <EmptyState
                icon={<ImageOff />}
                title="This profile isn’t available"
                description="It doesn’t exist, or the developer shows it to signed-in clients only."
                action={
                  signedIn ? undefined : (
                    <Button asChild>
                      <Link to={`/login?return_to=${encodeURIComponent(`/d/${id}`)}`}>
                        Sign in as a client
                      </Link>
                    </Button>
                  )
                }
              />
            ) : (
              <ErrorState
                requestId={profile.error instanceof ApiError ? profile.error.requestId : null}
                onRetry={() => void profile.refetch()}
              />
            )}
          </Card>
        ) : (
          <Profile p={profile.data} isMe={me.data?.id === profile.data.id} />
        )}
      </main>
      <SiteFooter />
    </div>
  );
}
