import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, useSearchParams } from "react-router";
import type { z } from "zod";
import { AuthLayout } from "@/components/AuthLayout";
import { Alert } from "@/components/ui/Feedback";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { PasswordMeter } from "@/components/ui/PasswordMeter";
import { useResetPassword } from "./api";
import { applyFieldErrors, messageFor } from "./errors";
import { PASSWORD_RULES } from "./PasswordRules";
import { resetSchema } from "./schemas";

type Values = z.infer<typeof resetSchema>;

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const reset = useResetPassword();
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(resetSchema) });
  const password = useWatch({ control: form.control, name: "new_password" });

  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      await reset.mutateAsync({ token, new_password: values.new_password });
      setDone(true);
    } catch (e) {
      if (!applyFieldErrors(e, form.setError, ["new_password"])) setError(messageFor(e));
    }
  });

  return (
    <AuthLayout title="Choose a new password" subtitle="You’ll be signed out of every device.">
      {done ? (
        <>
          <Alert tone="success">Your password is changed. Sign in with the new one.</Alert>
          <p className="mt-6 text-body-sm">
            <Link to="/login" className="font-medium text-primary">
              Sign in
            </Link>
          </p>
        </>
      ) : (
        <form noValidate onSubmit={(e) => void submit(e)} className="space-y-5">
          {error ? <Alert tone="danger">{error}</Alert> : null}
          <div className="space-y-2">
            <Field
              label="New password"
              type="password"
              autoComplete="new-password"
              hint={PASSWORD_RULES}
              error={form.formState.errors.new_password?.message}
              {...form.register("new_password")}
            />
            <PasswordMeter password={password} />
          </div>
          <Field
            label="Repeat new password"
            type="password"
            autoComplete="new-password"
            error={form.formState.errors.confirm?.message}
            {...form.register("confirm")}
          />
          <Button type="submit" full loading={form.formState.isSubmitting} disabled={!token}>
            Save new password
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
