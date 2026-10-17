import { useEffect, useState } from "react";
import { Navigate } from "react-router";
import { AuthLayout } from "@/components/AuthLayout";
import { Alert } from "@/components/ui/Feedback";
import { Button } from "@/components/ui/Button";
import { OtpInput } from "@/components/ui/OtpInput";
import { roleHome } from "@/lib/redirects";
import { useMe, useResendEmail, useSendOtp, useVerifyOtp } from "./api";
import { messageFor } from "./errors";

const RESEND_SECONDS = 60;

function useCountdown(start: number) {
  const [left, setLeft] = useState(start);
  useEffect(() => {
    if (left <= 0) return;
    const id = setTimeout(() => {
      setLeft((v) => v - 1);
    }, 1000);
    return () => {
      clearTimeout(id);
    };
  }, [left]);
  return [left, setLeft] as const;
}

/** Phone OTP + email status checklist; continues to the role home once both are done. */
export default function VerifyPage() {
  const me = useMe();
  const sendOtp = useSendOtp();
  const verifyOtp = useVerifyOtp();
  const resendEmail = useResendEmail();
  const [code, setCode] = useState("");
  const [message, setMessage] = useState<{ tone: "danger" | "success"; text: string } | null>(null);
  const [left, setLeft] = useCountdown(RESEND_SECONDS);

  if (me.isPending)
    return (
      <AuthLayout title="Verify your account">
        <p className="text-body text-text-muted">Loading…</p>
      </AuthLayout>
    );
  if (!me.data) return <Navigate to="/login?return_to=%2Fverify" replace />;
  if (me.data.status === "ACTIVE") return <Navigate to={roleHome(me.data.role)} replace />;
  const user = me.data;

  return (
    <AuthLayout
      title="Verify your account"
      subtitle="Two quick checks keep DevSync free of fake accounts."
    >
      <ol className="space-y-6">
        <li className="rounded-lg border border-border bg-surface p-5">
          <h2 className="text-body font-semibold text-text">
            {user.phone_verified ? "✓ Phone verified" : "1. Verify your phone"}
          </h2>
          {user.phone_verified ? null : (
            <form
              className="mt-4 space-y-4"
              noValidate
              onSubmit={(e) => {
                e.preventDefault();
                setMessage(null);
                verifyOtp.mutate(code, {
                  onSuccess: () => {
                    setMessage({ tone: "success", text: "Phone verified." });
                  },
                  onError: (err) => {
                    setMessage({ tone: "danger", text: messageFor(err) });
                  },
                });
              }}
            >
              <p className="text-body-sm text-text-muted">
                Enter the code we sent to {user.phone_e164 ?? "your phone"}.
              </p>
              <OtpInput label="Verification code" value={code} onChange={setCode} focusFirst />
              <div className="flex flex-wrap items-center gap-3">
                <Button type="submit" loading={verifyOtp.isPending} disabled={code.length !== 6}>
                  Verify phone
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={left > 0 || sendOtp.isPending}
                  onClick={() => {
                    sendOtp.mutate(undefined, {
                      onSuccess: () => {
                        setLeft(RESEND_SECONDS);
                        setMessage({ tone: "success", text: "We sent a new code." });
                      },
                      onError: (err) => {
                        setMessage({ tone: "danger", text: messageFor(err) });
                      },
                    });
                  }}
                >
                  {left > 0 ? `Send a new code in ${String(left)}s` : "Send a new code"}
                </Button>
              </div>
            </form>
          )}
        </li>
        <li className="rounded-lg border border-border bg-surface p-5">
          <h2 className="text-body font-semibold text-text">
            {user.email_verified ? "✓ Email verified" : "2. Verify your email"}
          </h2>
          {user.email_verified ? null : (
            <div className="mt-3 space-y-3">
              <p className="text-body-sm text-text-muted">
                Open the link we sent to {user.email}. It expires in 24 hours.
              </p>
              <Button
                variant="secondary"
                loading={resendEmail.isPending}
                onClick={() => {
                  resendEmail.mutate(undefined, {
                    onSuccess: () => {
                      setMessage({
                        tone: "success",
                        text: "We sent a new link. Older links no longer work.",
                      });
                    },
                    onError: (err) => {
                      setMessage({ tone: "danger", text: messageFor(err) });
                    },
                  });
                }}
              >
                Send a new link
              </Button>
              <Button variant="ghost" onClick={() => void me.refetch()}>
                I’ve verified my email
              </Button>
            </div>
          )}
        </li>
      </ol>
      <div className="mt-6" aria-live="polite">
        {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      </div>
    </AuthLayout>
  );
}
