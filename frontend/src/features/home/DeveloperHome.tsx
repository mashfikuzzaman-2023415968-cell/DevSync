import { Search } from "lucide-react";
import { Link } from "react-router";
import { NodeArt } from "@/components/brand/NodeArt";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, NewcomerBadge } from "@/components/ui/Display";
import { EmptyState, PageHeader } from "@/components/ui/Feedback";
import { useMe } from "@/features/auth/api";
import { usePortfolio, useSkillTests } from "@/features/profile/api";
import { Checklist } from "./Checklist";
import { firstName, greeting } from "./greeting";

/** Developer dashboard (spec §13.5 #9). Stats, invitations and recommendations join as their
 * phases arrive; the newcomer checklist works now. */
export default function DeveloperHome() {
  const me = useMe();
  const user = me.data;
  const portfolio = usePortfolio();
  const tests = useSkillTests();
  const hasPortfolio = (portfolio.data?.length ?? 0) > 0;
  const passedTest = tests.data?.some((t) => t.last_score !== null) === true;
  return (
    <>
      <PageHeader
        title={`${greeting()}, ${firstName(user?.display_name)}`}
        description="Here’s where your bids, invitations and active projects will show up."
        action={
          <Button asChild>
            <Link to="/dev/find">
              <Search aria-hidden="true" />
              Find projects
            </Link>
          </Button>
        }
      />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
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
        <Card>
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
      </div>
    </>
  );
}
