import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router";
import { AuthLayout } from "@/components/AuthLayout";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { PasswordMeter } from "@/components/ui/PasswordMeter";
import { useLogin, useRegister } from "./api";
import { applyFieldErrors, messageFor } from "./errors";
import { Honeypot } from "./Honeypot";
import { registerSchema, type RegisterValues } from "./schemas";
import { useBotCheck } from "./useBotCheck";

type Role = "CLIENT" | "DEVELOPER";

const ROLES: { value: Role; title: string; text: string }[] = [
  {
    value: "CLIENT",
    title: "I want to hire a team",
    text: "Plan a project, get a balanced team and pay by milestone.",
  },
  {
    value: "DEVELOPER",
    title: "I want to find work",
    text: "Bid on projects, join teams and build a reputation from real work.",
  },
];

export default function RegisterPage() {
  const [params] = useSearchParams();
  const preset = params.get("role")?.toUpperCase();
  const [role, setRole] = useState<Role | null>(
    preset === "CLIENT" || preset === "DEVELOPER" ? preset : null,
  );
  const [step, setStep] = useState<1 | 2>(role ? 2 : 1);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const register = useRegister();
  const login = useLogin();
  const bot = useBotCheck();
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { phone: "+880" },
  });
  const password = useWatch({ control: form.control, name: "password" });

  const submit = form.handleSubmit(async (values) => {
    if (!role) return;
    setError(null);
    try {
      const bots = await bot.fields(true);
      await register.mutateAsync({
        ...values,
        phone: values.phone.replace(/[\s-]/g, ""),
        role,
        ...bots,
      });
      // The answer is the same whether or not the email exists; signing in proves it was ours.
      await login.mutateAsync({
        email: values.email,
        password: values.password,
        ...(await bot.fields(false)),
      });
      void navigate("/verify", { replace: true });
    } catch (e) {
      if (!applyFieldErrors(e, form.setError, ["display_name", "email", "phone", "password"])) {
        setError(messageFor(e));
      }
    }
  });

  if (step === 1) {
    return (
      <AuthLayout title="Create your account" subtitle="First, what brings you to DevSync?">
        <fieldset className="space-y-3">
          <legend className="sr-only">Account type</legend>
          {ROLES.map((r) => (
            <label
              key={r.value}
              htmlFor={`role-${r.value}`}
              className={`flex min-h-11 cursor-pointer gap-3 rounded-lg border bg-surface p-4 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-primary ${role === r.value ? "border-primary bg-primary-soft" : "border-border hover:border-primary"}`}
            >
              <input
                id={`role-${r.value}`}
                type="radio"
                name="role"
                value={r.value}
                checked={role === r.value}
                onChange={() => {
                  setRole(r.value);
                }}
                className="mt-1 accent-[var(--primary)]"
              />
              <span>
                <span className="block text-body font-semibold text-text">{r.title}</span>
                <span className="block text-body-sm text-text-muted">{r.text}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <Button
          className="mt-6"
          full
          disabled={!role}
          onClick={() => {
            setStep(2);
          }}
        >
          Continue
        </Button>
        <p className="mt-6 text-body-sm text-text-muted">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-primary">
            Sign in
          </Link>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Your details"
      subtitle={
        role === "CLIENT" ? "You’re signing up to hire a team." : "You’re signing up to find work."
      }
    >
      <form noValidate onSubmit={(e) => void submit(e)} className="space-y-5">
        {error ? <Alert tone="danger">{error}</Alert> : null}
        <Field
          label="Full name"
          autoComplete="name"
          enterKeyHint="next"
          error={form.formState.errors.display_name?.message}
          {...form.register("display_name")}
        />
        <Field
          label="Email"
          type="email"
          inputMode="email"
          autoComplete="email"
          enterKeyHint="next"
          error={form.formState.errors.email?.message}
          {...form.register("email")}
        />
        <Field
          label="Mobile number"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          hint="We’ll text you a 6-digit code. One account per number."
          enterKeyHint="next"
          error={form.formState.errors.phone?.message}
          {...form.register("phone")}
        />
        <div className="space-y-2">
          <Field
            label="Password"
            type="password"
            autoComplete="new-password"
            enterKeyHint="next"
            error={form.formState.errors.password?.message}
            {...form.register("password")}
          />
          <PasswordMeter password={password} />
        </div>
        <label className="flex min-h-11 items-start gap-3 text-body-sm text-text">
          <input
            type="checkbox"
            className="mt-1 accent-[var(--primary)]"
            {...form.register("accept_terms")}
          />
          <span>
            I agree to the terms of use and understand that payments on DevSync are simulated.
          </span>
        </label>
        {form.formState.errors.accept_terms ? (
          <p className="text-caption text-danger" role="alert">
            {form.formState.errors.accept_terms.message}
          </p>
        ) : null}
        <Honeypot value={bot.honeypot} onChange={bot.setHoneypot} />
        <Button type="submit" full loading={form.formState.isSubmitting}>
          {bot.solving ? "Checking…" : "Create account"}
        </Button>
        <button
          type="button"
          className="min-h-11 text-body-sm text-primary"
          onClick={() => {
            setStep(1);
          }}
        >
          Change account type
        </button>
      </form>
    </AuthLayout>
  );
}
