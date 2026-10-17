/** Public project list (spec §13.5 #6). Projects open for bids appear here from Phase 4–5;
 * until then the page explains what will show and how to get ready. */
import { Link } from "react-router";
import { Still } from "@/components/brand/Still";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Display";
import { EmptyState } from "@/components/ui/Feedback";
import { SiteFooter } from "@/features/landing/SiteFooter";
import { SiteHeader } from "@/features/landing/SiteHeader";

export default function PublicProjectsPage() {
  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <SiteHeader />
      <main id="main" className="mx-auto w-full max-w-content flex-1 px-4 pb-20 pt-28 sm:px-6">
        <h1 className="text-h1 font-semibold tracking-tight text-text">Browse projects</h1>
        <p className="mt-2 max-w-2xl text-lead text-text-muted">
          Software projects looking for a team, with the budget, team size, skills and deadline of
          each.
        </p>
        <Card className="mt-10">
          <EmptyState
            art={<Still name="team" className="w-60" />}
            title="No projects are open for bids yet"
            description="When clients publish projects they’ll be listed here. Create a developer account now so you’re ready to bid."
            action={
              <div className="flex flex-col gap-3 sm:flex-row">
                <Button asChild>
                  <Link to="/register?role=developer">Create a developer account</Link>
                </Button>
                <Button asChild variant="outline">
                  <Link to="/register?role=client">Post a project</Link>
                </Button>
              </div>
            }
          />
        </Card>
      </main>
      <SiteFooter />
    </div>
  );
}
