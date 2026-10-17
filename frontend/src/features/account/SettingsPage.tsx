import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";
import type { z } from "zod";
import { AppFrame } from "@/components/AppFrame";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { useChangePassword, useLogout, useRevokeSession, useSessions } from "@/features/auth/api";
import { applyFieldErrors, messageFor } from "@/features/auth/errors";
import { changePasswordSchema } from "@/features/auth/schemas";

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Dhaka",
});

/** Security settings: signed-in devices, sign out everywhere, change password (spec §13.5 #19). */
export default function SettingsPage() {
  const sessions = useSessions();
  const revoke = useRevokeSession();
  const logoutAll = useLogout(true);
  const change = useChangePassword();
  const navigate = useNavigate();
  const [notice, setNotice] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const form = useForm<z.infer<typeof changePasswordSchema>>({
    resolver: zodResolver(changePasswordSchema),
  });

  const submit = form.handleSubmit(async (values) => {
    setNotice(null);
    try {
      await change.mutateAsync(values);
      form.reset();
      setNotice({ tone: "success", text: "Password changed. Other devices were signed out." });
      void sessions.refetch();
    } catch (e) {
      if (!applyFieldErrors(e, form.setError, ["new_password"]))
        setNotice({ tone: "danger", text: messageFor(e) });
    }
  });

  return (
    <AppFrame title="Settings" description="Your security and signed-in devices.">
      <div className="grid gap-6 lg:grid-cols-2">
        <section
          aria-labelledby="devices"
          className="rounded-lg border border-border bg-surface p-6 shadow-xs"
        >
          <h2 id="devices" className="text-h4 font-semibold text-text">
            Signed-in devices
          </h2>
          {sessions.isPending ? (
            <p className="mt-4 text-body-sm text-text-muted">Loading devices…</p>
          ) : null}
          {sessions.isError ? (
            <div className="mt-4">
              <Alert tone="danger">{messageFor(sessions.error)}</Alert>
            </div>
          ) : null}
          <ul className="mt-4 divide-y divide-border">
            {sessions.data?.items.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-body-sm font-medium text-text">
                    {s.user_agent ?? "Unknown browser"}
                  </p>
                  <p className="text-caption text-text-muted">
                    {s.current
                      ? "This device"
                      : `Last active ${dateFormat.format(new Date(s.last_seen_at))}`}
                    {s.ip ? `, ${s.ip}` : ""}
                  </p>
                </div>
                {s.current ? null : (
                  <Button
                    variant="secondary"
                    loading={revoke.isPending && revoke.variables === s.id}
                    onClick={() => {
                      revoke.mutate(s.id);
                    }}
                  >
                    Sign out
                  </Button>
                )}
              </li>
            ))}
          </ul>
          <Button
            className="mt-4"
            variant="danger"
            loading={logoutAll.isPending}
            onClick={() => {
              logoutAll.mutate(undefined, {
                onSettled: () => void navigate("/", { replace: true }),
              });
            }}
          >
            Sign out of every device
          </Button>
        </section>
        <section
          aria-labelledby="password"
          className="rounded-lg border border-border bg-surface p-6 shadow-xs"
        >
          <h2 id="password" className="text-h4 font-semibold text-text">
            Change password
          </h2>
          <form noValidate onSubmit={(e) => void submit(e)} className="mt-4 space-y-4">
            {notice ? <Alert tone={notice.tone}>{notice.text}</Alert> : null}
            <Field
              label="Current password"
              type="password"
              autoComplete="current-password"
              error={form.formState.errors.current_password?.message}
              {...form.register("current_password")}
            />
            <Field
              label="New password"
              type="password"
              autoComplete="new-password"
              error={form.formState.errors.new_password?.message}
              {...form.register("new_password")}
            />
            <Button type="submit" loading={form.formState.isSubmitting}>
              Change password
            </Button>
          </form>
        </section>
      </div>
    </AppFrame>
  );
}
