import { CirclePlus } from "lucide-react";
import { Link } from "react-router";
import { NodeArt } from "@/components/brand/NodeArt";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Display";
import { EmptyState, PageHeader } from "@/components/ui/Feedback";
import { useMe } from "@/features/auth/api";
import { Checklist } from "./Checklist";
import { firstName, greeting } from "./greeting";

/** Client dashboard (spec §13.5 #20). Project stats and activity join with Phase 4+. */
export default function ClientHome() {
  const me = useMe();
  const user = me.data;
  return (
    <>
      <PageHeader
        title={`${greeting()}, ${firstName(user?.display_name)}`}
        description="Plan a project, get a balanced team and pay by milestone."
        action={
          <Button asChild>
            <Link to="/client/projects/new">
              <CirclePlus aria-hidden="true" />
              Create project
            </Link>
          </Button>
        }
      />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <Card>
          <EmptyState
            art={<NodeArt />}
            title="No projects yet"
            description="Describe the work, split it into milestones and DevSync shows the critical path before anyone bids."
            action={
              <Button asChild variant="outline">
                <Link to="/client/projects/new">Plan your first project</Link>
              </Button>
            }
          />
        </Card>
        <Card>
          <CardHeader
            title="Before you publish"
            description="Both checks keep the marketplace trustworthy."
          />
          <div className="mt-2">
            <Checklist
              items={[
                {
                  label: "Verify your phone",
                  done: user?.phone_verified === true,
                  hint: "One account per number.",
                  to: "/verify",
                },
                {
                  label: "Verify your email",
                  done: user?.email_verified === true,
                  hint: "Bids, invitations and approvals are sent there.",
                  to: "/verify",
                },
              ]}
            />
          </div>
        </Card>
      </div>
    </>
  );
}
