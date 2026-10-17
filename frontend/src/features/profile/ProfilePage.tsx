/** Profile & portfolio (spec §13.5 #15): what clients see when they consider a developer. */
import { ExternalLink } from "lucide-react";
import { Link } from "react-router";
import { Button } from "@/components/ui/Button";
import { Card, Skeleton } from "@/components/ui/Display";
import { ErrorState, PageHeader } from "@/components/ui/Feedback";
import { ApiError } from "@/api/client";
import { useMe } from "@/features/auth/api";
import { useDeveloperProfile, usePortfolio, useSkills, useSkillTests } from "./api";
import { AboutCard } from "./AboutCard";
import { CertificatesCard, ExternalReviewsCard } from "./EvidenceCards";
import { PortfolioCard } from "./PortfolioCard";
import { SkillsCard } from "./SkillsCard";

function CardSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <Card className="space-y-3 p-5" aria-hidden="true">
      <Skeleton className="h-5 w-40" />
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-11" />
      ))}
    </Card>
  );
}

export default function ProfilePage() {
  const me = useMe();
  const profile = useDeveloperProfile();
  const skills = useSkills();
  const portfolio = usePortfolio();
  const tests = useSkillTests();
  const failed = [profile, skills, portfolio].find((q) => q.isError);

  return (
    <>
      <PageHeader
        title="Profile & portfolio"
        description="Your headline, skills and work, as clients will see them."
        action={
          me.data ? (
            <Button asChild variant="outline" icon={<ExternalLink aria-hidden="true" />}>
              <Link to={`/d/${me.data.id}`}>View public profile</Link>
            </Button>
          ) : null
        }
      />
      {failed ? (
        <Card>
          <ErrorState
            requestId={failed.error instanceof ApiError ? failed.error.requestId : null}
            onRetry={() => {
              void profile.refetch();
              void skills.refetch();
              void portfolio.refetch();
            }}
          />
        </Card>
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
          <div className="space-y-6">
            {profile.data ? <AboutCard profile={profile.data} /> : <CardSkeleton rows={5} />}
            {portfolio.data && skills.data ? (
              <PortfolioCard items={portfolio.data} skills={skills.data} />
            ) : (
              <CardSkeleton />
            )}
            <CertificatesCard />
            <ExternalReviewsCard />
          </div>
          <div>
            {profile.data && skills.data ? (
              <SkillsCard skills={skills.data} mine={profile.data.skills} tests={tests.data} />
            ) : (
              <CardSkeleton rows={6} />
            )}
          </div>
        </div>
      )}
    </>
  );
}
