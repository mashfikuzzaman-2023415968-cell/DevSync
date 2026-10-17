import { AppFrame } from "@/components/AppFrame";

/** Admin area placeholder. This module is a separate chunk, downloaded only after
 * `/me` confirms an admin with a TOTP-verified session (spec §14.17). */
export default function AdminHome() {
  return (
    <AppFrame title="Administration" description="The admin console arrives in a later phase.">
      <section className="max-w-2xl rounded-lg border border-border bg-surface p-6 shadow-xs">
        <p className="text-body text-text-muted">
          Your session is verified with two-step authentication.
        </p>
      </section>
    </AppFrame>
  );
}
