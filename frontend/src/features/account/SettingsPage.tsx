/** Settings (spec §13.5 #19): account name, appearance (theme, reduced motion), signed-in
 * devices, change password. Data export and account deletion arrive with Phase 12. */
import { zodResolver } from "@hookform/resolvers/zod";
import { LaptopMinimal, LogOut, Monitor, Moon, Sun } from "lucide-react";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useNavigate } from "react-router";
import type { z } from "zod";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { Alert, ErrorState, PageHeader } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Switch } from "@/components/ui/Choice";
import { ConfirmDialog } from "@/components/ui/Overlay";
import { PasswordMeter } from "@/components/ui/PasswordMeter";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { toast } from "@/components/ui/toast-store";
import { usePreferences, type ThemePref } from "@/design/preferences";
import {
  useChangePassword,
  useLogout,
  useMe,
  useRevokeSession,
  useSessions,
  useUpdateMe,
} from "@/features/auth/api";
import { applyFieldErrors, messageFor } from "@/features/auth/errors";
import { PASSWORD_RULES } from "@/features/auth/PasswordRules";
import { changePasswordSchema, profileSchema } from "@/features/auth/schemas";
import { formatDateTime, formatRelative } from "@/lib/format";

function ProfileCard() {
  const me = useMe();
  const update = useUpdateMe();
  const form = useForm<z.infer<typeof profileSchema>>({
    resolver: zodResolver(profileSchema),
    values: { display_name: me.data?.display_name ?? "" },
  });
  const submit = form.handleSubmit(async (values) => {
    try {
      await update.mutateAsync(values);
      toast({ tone: "success", title: "Name saved" });
    } catch (e) {
      if (!applyFieldErrors(e, form.setError, ["display_name"]))
        form.setError("display_name", { message: messageFor(e) });
    }
  });
  return (
    <Card>
      <CardHeader
        title="Your account"
        description={<span data-volatile="">{me.data?.email}</span>}
      />
      <form noValidate onSubmit={(e) => void submit(e)} className="space-y-4 p-5">
        <Field
          label="Full name"
          autoComplete="name"
          error={form.formState.errors.display_name?.message}
          {...form.register("display_name")}
        />
        <Button type="submit" variant="outline" loading={form.formState.isSubmitting}>
          Save name
        </Button>
      </form>
    </Card>
  );
}

const THEMES = [
  {
    value: "light",
    label: (
      <span className="inline-flex items-center gap-1.5">
        <Sun className="size-4" aria-hidden="true" />
        Light
      </span>
    ),
  },
  {
    value: "dark",
    label: (
      <span className="inline-flex items-center gap-1.5">
        <Moon className="size-4" aria-hidden="true" />
        Dark
      </span>
    ),
  },
  {
    value: "system",
    label: (
      <span className="inline-flex items-center gap-1.5">
        <Monitor className="size-4" aria-hidden="true" />
        System
      </span>
    ),
  },
] as const;

function AppearanceCard() {
  const { theme, setTheme, motion, setMotion } = usePreferences();
  return (
    <Card>
      <CardHeader title="Appearance" description="Saved on this device." />
      <div className="space-y-5 p-5">
        <div>
          <p className="mb-2 text-body-sm font-medium text-text">Theme</p>
          <SegmentedControl<ThemePref>
            label="Theme"
            value={theme}
            onChange={setTheme}
            segments={THEMES}
            className="w-full sm:w-auto"
          />
        </div>
        <Switch
          label="Reduce motion"
          description="Turns off movement such as slides, count-ups and the 3D scene. Your device setting is always respected too."
          checked={motion === "reduce"}
          onCheckedChange={(on) => {
            setMotion(on ? "reduce" : "system");
          }}
        />
      </div>
    </Card>
  );
}

function DevicesCard() {
  const sessions = useSessions();
  const revoke = useRevokeSession();
  const logoutAll = useLogout(true);
  const navigate = useNavigate();
  return (
    <Card>
      <CardHeader title="Signed-in devices" description="Sign out anywhere you don’t recognise." />
      <div className="p-5 pt-3">
        {sessions.isPending ? (
          <div className="space-y-3" aria-label="Loading devices" role="status">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : null}
        {sessions.isError ? (
          <ErrorState
            title="Devices didn’t load"
            onRetry={() => void sessions.refetch()}
            requestId={null}
          />
        ) : null}
        <ul className="divide-y divide-border" data-volatile="">
          {sessions.data?.items.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-4 py-3">
              <div className="flex min-w-0 items-start gap-3">
                <LaptopMinimal
                  className="mt-0.5 size-5 shrink-0 text-text-subtle"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="truncate text-body-sm font-medium text-text">
                    {s.user_agent ?? "Unknown browser"}
                  </p>
                  <p className="text-caption text-text-muted">
                    {s.current ? (
                      "This device"
                    ) : (
                      <time dateTime={s.last_seen_at} title={formatDateTime(s.last_seen_at)}>
                        Active {formatRelative(s.last_seen_at)}
                      </time>
                    )}
                    {s.ip ? `, ${s.ip}` : ""}
                  </p>
                </div>
              </div>
              {s.current ? null : (
                <Button
                  variant="outline"
                  size="sm"
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
        <ConfirmDialog
          trigger={
            <Button className="mt-4" variant="destructive" icon={<LogOut aria-hidden="true" />}>
              Sign out of every device
            </Button>
          }
          title="Sign out of every device?"
          description="You’ll be signed out here too, and anyone using your account elsewhere loses access immediately."
          confirmLabel="Sign out everywhere"
          onConfirm={() =>
            logoutAll.mutateAsync().finally(() => {
              void navigate("/", { replace: true });
            })
          }
        />
      </div>
    </Card>
  );
}

function PasswordCard() {
  const change = useChangePassword();
  const [notice, setNotice] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const form = useForm<z.infer<typeof changePasswordSchema>>({
    resolver: zodResolver(changePasswordSchema),
  });
  const next = useWatch({ control: form.control, name: "new_password" });
  const submit = form.handleSubmit(async (values) => {
    setNotice(null);
    try {
      await change.mutateAsync(values);
      form.reset();
      setNotice({ tone: "success", text: "Password changed. Your other devices were signed out." });
    } catch (e) {
      if (!applyFieldErrors(e, form.setError, ["current_password", "new_password"]))
        setNotice({ tone: "danger", text: messageFor(e) });
    }
  });
  return (
    <Card>
      <CardHeader
        title="Change password"
        description="Other devices are signed out when you change it."
      />
      <form noValidate onSubmit={(e) => void submit(e)} className="space-y-4 p-5">
        {notice ? <Alert tone={notice.tone}>{notice.text}</Alert> : null}
        <Field
          label="Current password"
          type="password"
          autoComplete="current-password"
          error={form.formState.errors.current_password?.message}
          {...form.register("current_password")}
        />
        <div className="space-y-2">
          <Field
            label="New password"
            type="password"
            autoComplete="new-password"
            hint={PASSWORD_RULES}
            error={form.formState.errors.new_password?.message}
            {...form.register("new_password")}
          />
          <PasswordMeter password={next} />
        </div>
        <Button type="submit" loading={form.formState.isSubmitting}>
          Change password
        </Button>
      </form>
    </Card>
  );
}

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Your account, appearance and security." />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-2">
        <div className="space-y-6">
          <ProfileCard />
          <AppearanceCard />
        </div>
        <div className="space-y-6">
          <DevicesCard />
          <PasswordCard />
        </div>
      </div>
    </>
  );
}
