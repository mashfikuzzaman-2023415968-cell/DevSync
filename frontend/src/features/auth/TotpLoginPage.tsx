import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { AuthLayout } from "@/components/AuthLayout";
import { Alert } from "@/components/ui/Feedback";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { OtpInput } from "@/components/ui/OtpInput";
import { safeRedirect } from "@/lib/redirects";
import { useTotpLogin } from "./api";
import { messageFor } from "./errors";

interface State {
  preAuth?: string;
  returnTo?: string | null;
}

export default function TotpLoginPage() {
  const location = useLocation();
  const state = (location.state ?? {}) as State;
  const navigate = useNavigate();
  const totp = useTotpLogin();
  const [code, setCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [recovery, setRecovery] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!state.preAuth) return <Navigate to="/login" replace />;
  const preAuth = state.preAuth;

  const submit = async () => {
    setError(null);
    try {
      const result = await totp.mutateAsync({
        pre_auth: preAuth,
        ...(useRecovery ? { recovery_code: recovery } : { code }),
        return_to: state.returnTo ?? null,
      });
      void navigate(safeRedirect(result.redirect_to, "ADMIN"), { replace: true });
    } catch (e) {
      setError(messageFor(e));
    }
  };

  return (
    <AuthLayout title="Two-step verification" subtitle="Admin accounts need a second factor.">
      <form
        noValidate
        className="space-y-5"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        {error ? <Alert tone="danger">{error}</Alert> : null}
        {useRecovery ? (
          <Field
            label="Recovery code"
            autoComplete="off"
            value={recovery}
            onChange={(e) => {
              setRecovery(e.target.value);
            }}
            hint="Each recovery code works once."
          />
        ) : (
          <OtpInput
            label="Code from your authenticator app"
            value={code}
            onChange={setCode}
            focusFirst
          />
        )}
        <Button
          type="submit"
          full
          loading={totp.isPending}
          disabled={useRecovery ? recovery.length < 8 : code.length !== 6}
        >
          Verify and sign in
        </Button>
        <button
          type="button"
          className="min-h-11 text-body-sm text-primary"
          onClick={() => {
            setUseRecovery((v) => !v);
            setError(null);
          }}
        >
          {useRecovery ? "Use the authenticator app instead" : "Use a recovery code instead"}
        </button>
      </form>
    </AuthLayout>
  );
}
