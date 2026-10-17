import { useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { AuthLayout } from "@/components/AuthLayout";
import { Alert } from "@/components/ui/Feedback";
import { Button } from "@/components/ui/Button";
import { OtpInput } from "@/components/ui/OtpInput";
import { useMe, useTotpConfirm, useTotpSetup } from "@/features/auth/api";
import { messageFor } from "@/features/auth/errors";

/** Forced first-time TOTP setup for admins (spec §13.4 guards, §14.4). */
export default function SetupTwoFactorPage() {
  const me = useMe();
  const setup = useTotpSetup();
  const confirm = useTotpConfirm();
  const navigate = useNavigate();
  const [code, setCode] = useState("");

  if (me.data && me.data.role !== "ADMIN") return <Navigate to="/403" replace />;

  return (
    <AuthLayout
      title="Set up two-step verification"
      subtitle="Admin accounts must use an authenticator app."
    >
      {confirm.data ? (
        <div className="space-y-4">
          <Alert tone="success">
            Two-step verification is on. Save these recovery codes somewhere safe; each works once
            and they won’t be shown again.
          </Alert>
          <ul className="grid grid-cols-2 gap-2 rounded-lg border border-border bg-surface p-4 font-mono text-body-sm">
            {confirm.data.recovery_codes.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          <Button full onClick={() => void navigate("/admin", { replace: true })}>
            I’ve saved my codes
          </Button>
        </div>
      ) : (
        <div className="space-y-5">
          {setup.data ? (
            <>
              <p className="text-body-sm text-text-muted">
                Add DevSync to your authenticator app with this key, then enter the 6-digit code it
                shows.
              </p>
              <p className="break-all rounded-md bg-surface-2 p-3 font-mono text-body-sm text-text">
                {setup.data.secret}
              </p>
              <OtpInput label="Code from your authenticator app" value={code} onChange={setCode} />
              {confirm.isError ? <Alert tone="danger">{messageFor(confirm.error)}</Alert> : null}
              <Button
                full
                loading={confirm.isPending}
                disabled={code.length !== 6}
                onClick={() => {
                  confirm.mutate(code);
                }}
              >
                Turn on two-step verification
              </Button>
            </>
          ) : (
            <>
              {setup.isError ? <Alert tone="danger">{messageFor(setup.error)}</Alert> : null}
              <Button
                full
                loading={setup.isPending}
                onClick={() => {
                  setup.mutate();
                }}
              >
                Create my authenticator key
              </Button>
            </>
          )}
        </div>
      )}
    </AuthLayout>
  );
}
