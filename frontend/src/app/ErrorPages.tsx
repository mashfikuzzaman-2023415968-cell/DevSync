import { Link } from "react-router";
import { AuthLayout } from "@/components/AuthLayout";

export function NotFoundPage() {
  return (
    <AuthLayout title="Page not found" subtitle="The link may be old or mistyped.">
      <Link to="/" className="font-medium text-primary">
        Go to the homepage
      </Link>
    </AuthLayout>
  );
}

export function ForbiddenPage() {
  return (
    <AuthLayout
      title="This area isn't for your account"
      subtitle="Sign in with a different account or go back to your home page."
    >
      <Link to="/" className="font-medium text-primary">
        Go to the homepage
      </Link>
    </AuthLayout>
  );
}
