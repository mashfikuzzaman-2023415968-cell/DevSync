/**
 * Notification switches on Settings (spec §12, §13.5 #19; D153, D162): one row per §12 kind,
 * with an in-app switch and, where §12 has an email, an email switch. Each change saves at
 * once (and moves back with the reason if it can't). Account and security emails are always
 * sent and can't be switched off; the card says so.
 */
import { ApiError } from "@/api/client";
import type { PreferenceItem } from "@/api/types";
import { Switch } from "@/components/ui/Choice";
import { Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { ErrorState } from "@/components/ui/Feedback";
import { toast } from "@/components/ui/toast-store";
import { messageFor } from "@/features/auth/errors";
import { useNotificationPreferences, useSavePreference } from "./api";

export function NotificationPreferencesCard() {
  const q = useNotificationPreferences();
  const save = useSavePreference();
  const change = (row: PreferenceItem, next: { in_app?: boolean; email?: boolean }) => {
    save.mutate(
      { category: row.category, in_app: next.in_app ?? row.in_app, email: next.email ?? row.email },
      {
        onError: (e) => {
          toast({ tone: "danger", title: messageFor(e) });
        },
      },
    );
  };
  return (
    <Card>
      <CardHeader
        title="Notifications"
        description="Choose what reaches you in DevSync and by email. Account and security emails, such as password resets, are always sent."
      />
      <div className="px-5 pb-5">
        {q.isPending ? (
          <div className="space-y-3" aria-busy="true" aria-label="Loading notification settings">
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-full" />
          </div>
        ) : q.isError ? (
          <ErrorState
            title="Your notification settings didn’t load"
            requestId={q.error instanceof ApiError ? q.error.requestId : null}
            onRetry={() => void q.refetch()}
          />
        ) : (
          <ul className="divide-y divide-border">
            {q.data.items.map((row) => (
              <li key={row.category} className="py-3">
                <p className="mb-1 text-body-sm font-medium text-text">{row.label}</p>
                <div className="grid gap-x-6 sm:grid-cols-2">
                  <Switch
                    label="In DevSync"
                    aria-label={`${row.label}: in DevSync`}
                    checked={row.in_app}
                    onCheckedChange={(on) => {
                      change(row, { in_app: on });
                    }}
                  />
                  {row.email_available ? (
                    <Switch
                      label="By email"
                      aria-label={`${row.label}: by email`}
                      checked={row.email}
                      onCheckedChange={(on) => {
                        change(row, { email: on });
                      }}
                    />
                  ) : (
                    <p className="flex min-h-11 items-center text-caption text-text-muted">
                      No email for this one
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
