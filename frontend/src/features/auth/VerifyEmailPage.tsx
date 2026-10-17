import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router";
import { AuthLayout } from "@/components/AuthLayout";
import { Alert } from "@/components/ui/Alert";
import { useVerifyEmail } from "./api";
import { messageFor } from "./errors";

/** Landing page for the email link: confirms the token once, then points onward. */
export default function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const verify = useVerifyEmail();
  const sent = useRef(false);

  useEffect(() => {
    if (!sent.current && token) {
      sent.current = true;
      verify.mutate(token);
    }
  }, [token, verify]);

  return (
    <AuthLayout title="Email verification">
      {!token ? (
        <Alert tone="danger">This link is incomplete. Open the latest email from DevSync.</Alert>
      ) : null}
      {verify.isPending ? (
        <p className="text-body text-text-muted">Confirming your email…</p>
      ) : null}
      {verify.isSuccess ? <Alert tone="success">Your email is verified.</Alert> : null}
      {verify.isError ? <Alert tone="danger">{messageFor(verify.error)}</Alert> : null}
      <p className="mt-6 text-body-sm">
        <Link to="/verify" className="font-medium text-primary">
          Continue
        </Link>
      </p>
    </AuthLayout>
  );
}
