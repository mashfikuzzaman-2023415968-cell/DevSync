import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { AuthLayout } from "@/components/AuthLayout";
import { Alert } from "@/components/ui/Feedback";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { isSafePath, safeRedirect } from "@/lib/redirects";
import { useLogin } from "./api";
import { messageFor } from "./errors";
import { Honeypot } from "./Honeypot";
import { loginSchema, type LoginValues } from "./schemas";
import { useBotCheck } from "./useBotCheck";

export default function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const returnTo = params.get("return_to");
  const login = useLogin();
  const bot = useBotCheck();
  const [needsCaptcha, setNeedsCaptcha] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  const submit = form.handleSubmit(async (values) => {
    setFormError(null);
    const attempt = async (withCaptcha: boolean) =>
      login.mutateAsync({
        ...values,
        ...(await bot.fields(withCaptcha)),
        return_to: isSafePath(returnTo) ? returnTo : null,
      });
    try {
      let result;
      try {
        result = await attempt(needsCaptcha);
      } catch (error) {
        // After repeated failures (and always for admins) the server asks for the check.
        if (error instanceof ApiError && error.details.captcha_required === true) {
          setNeedsCaptcha(true);
          result = await attempt(true);
        } else {
          throw error;
        }
      }
      if (result.status === "TOTP_REQUIRED" && result.pre_auth) {
        void navigate("/login/totp", { state: { preAuth: result.pre_auth, returnTo } });
        return;
      }
      void navigate(safeRedirect(result.redirect_to, null), { replace: true });
    } catch (error) {
      setFormError(messageFor(error));
    }
  });

  return (
    <AuthLayout title="Sign in" subtitle="Welcome back. Pick up where your projects left off.">
      <form noValidate onSubmit={(e) => void submit(e)} className="space-y-5">
        {formError ? <Alert tone="danger">{formError}</Alert> : null}
        <Field
          label="Email"
          type="email"
          autoComplete="email"
          inputMode="email"
          enterKeyHint="next"
          error={form.formState.errors.email?.message}
          {...form.register("email")}
        />
        <div className="space-y-1.5">
          <Field
            label="Password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            enterKeyHint="go"
            error={form.formState.errors.password?.message}
            {...form.register("password")}
          />
          <div className="flex items-center justify-between">
            <button
              type="button"
              className="min-h-11 rounded-md text-body-sm text-primary"
              onClick={() => {
                setShowPassword((v) => !v);
              }}
              aria-pressed={showPassword}
            >
              {showPassword ? "Hide password" : "Show password"}
            </button>
            <Link
              to="/forgot-password"
              className="inline-flex min-h-11 items-center text-body-sm font-medium text-primary hover:underline"
            >
              Forgot password?
            </Link>
          </div>
        </div>
        <Honeypot value={bot.honeypot} onChange={bot.setHoneypot} />
        {needsCaptcha ? (
          <p className="text-caption text-text-muted">
            We’ll run a quick automatic check that you’re not a bot.
          </p>
        ) : null}
        <Button type="submit" full loading={form.formState.isSubmitting}>
          {bot.solving ? "Checking…" : "Sign in"}
        </Button>
        <p className="text-body-sm text-text-muted">
          New to DevSync?{" "}
          <Link to="/register" className="font-medium text-primary">
            Create an account
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
