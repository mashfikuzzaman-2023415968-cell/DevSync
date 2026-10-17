import { Skeleton } from "@/components/ui/Display";

/** Loading layout matching the shell's page structure (spec §13.8 #8: skeletons, not spinners). */
export function PageSkeleton() {
  return (
    <div className="min-h-dvh bg-bg" role="status" aria-label="Loading">
      <div className="h-16 border-b border-border bg-surface" />
      <div className="mx-auto max-w-content space-y-6 px-4 py-8 sm:px-6">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-5 w-80 max-w-full" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-64 rounded-lg" />
      </div>
    </div>
  );
}
