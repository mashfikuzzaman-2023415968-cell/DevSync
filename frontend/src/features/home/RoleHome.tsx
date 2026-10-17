import { AppFrame } from "@/components/AppFrame";
import { useMe } from "@/features/auth/api";

const COPY = {
  CLIENT: {
    title: "Your projects",
    body: "Project planning arrives soon: you'll break work into milestones, see the critical path and invite a fair team.",
  },
  DEVELOPER: {
    title: "Your work",
    body: "Your profile, skill challenges and project search arrive soon. Verified accounts will be able to bid on projects.",
  },
} as const;

/** Placeholder role homes for Phase 1 (dashboards come in later phases). */
export default function RoleHome({ kind }: { kind: "CLIENT" | "DEVELOPER" }) {
  const me = useMe();
  const copy = COPY[kind];
  return (
    <AppFrame title={`Hello, ${me.data?.display_name ?? ""}`} description={copy.title}>
      <section className="max-w-2xl rounded-lg border border-border bg-surface p-6 shadow-xs">
        <p className="text-body text-text-muted">{copy.body}</p>
      </section>
    </AppFrame>
  );
}
