import { ShieldCheck } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Display";
import { PageHeader } from "@/components/ui/Feedback";

/** Admin dashboard placeholder until the console arrives (Phase 12). */
export default function AdminHome() {
  return (
    <>
      <PageHeader
        title="Administration"
        description="Platform health, disputes and integrity flags will appear here."
      />
      <Card className="max-w-2xl">
        <CardHeader
          title="Your session is protected"
          description="You signed in with two-step authentication. Sensitive actions ask for a fresh code."
          action={<ShieldCheck className="size-6 text-success" aria-hidden="true" />}
        />
        <p className="px-5 pb-5 pt-3 text-body-sm text-text-muted">
          The admin console (users, disputes, flags, settings and the audit log) is built in Phase
          12. The menu already lists every section.
        </p>
      </Card>
    </>
  );
}
