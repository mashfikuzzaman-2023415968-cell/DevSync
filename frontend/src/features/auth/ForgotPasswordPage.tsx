import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import type { z } from "zod";
import { AuthLayout } from "@/components/AuthLayout";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { useForgotPassword } from "./api";
import { messageFor } from "./errors";
import { Honeypot } from "./Honeypot";
import { forgotSchema } from "./schemas";
import { useBotCheck } from "./useBotCheck";

export default function ForgotPasswordPage() {
  const forgot = useForgotPassword();
  const bot = useBotCheck();
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof forgotSchema>>({ resolver: zodResolver(forgotSchema) });

  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const result = await forgot.mutateAsync({ ...values, ...(await bot.fields(true)) });
      setDone(result.message);
    } catch (e) {
      setError(messageFor(e));
    }
  });

  return (
    <AuthLayout title="Reset your password" subtitle="We’ll email you a link to choose a new one.">
      {done ? (
        <Alert tone="success">{done}</Alert>
      ) : (
        <form noValidate onSubmit={(e) => void submit(e)} className="space-y-5">
          {error ? <Alert tone="danger">{error}</Alert> : null}
          <Field
            label="Email"
            type="email"
            inputMode="email"
            autoComplete="email"
            error={form.formState.errors.email?.message}
            {...form.register("email")}
          />
          <Honeypot value={bot.honeypot} onChange={bot.setHoneypot} />
          <Button type="submit" full loading={form.formState.isSubmitting}>
            {bot.solving ? "Checking…" : "Email me a reset link"}
          </Button>
        </form>
      )}
      <p className="mt-6 text-body-sm">
        <Link to="/login" className="font-medium text-primary">
          Back to sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
