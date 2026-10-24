import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useMe } from "@/features/auth/api";
import { PageSkeleton } from "@/components/shell/PageSkeleton";
import { ErrorState } from "@/components/ui/Feedback";
import { roleHome } from "@/lib/redirects";
import { signedOutReason } from "@/lib/sessionNotice";

const Loading = PageSkeleton;

/** Route guard (spec §13.4): signed out → login with return_to; PENDING → /verify;
 * wrong role → /403; admins without TOTP → /admin/setup-2fa. The server re-checks
 * everything; this only decides what to show. */
export function RequireAuth({
  roles,
  allowPending = false,
  children,
}: {
  roles?: readonly string[];
  allowPending?: boolean;
  children: ReactNode;
}) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <Loading />;
  // The server couldn't say who is signed in (outage, timeout): that isn't "signed out".
  if (me.isError && me.data === undefined)
    return <AccountError onRetry={() => void me.refetch()} />;
  if (!me.data) {
    const returnTo = encodeURIComponent(location.pathname + location.search);
    // Say why when the session just ended (expired or suspended), spec §13.4.
    const reason = signedOutReason();
    const why = reason ? `&reason=${reason}` : "";
    return <Navigate to={`/login?return_to=${returnTo}${why}`} replace />;
  }
  if (me.data.status === "PENDING" && !allowPending) return <Navigate to="/verify" replace />;
  if (roles && !roles.includes(me.data.role)) return <Navigate to="/403" replace />;
  if (
    me.data.role === "ADMIN" &&
    !me.data.totp_verified &&
    location.pathname !== "/admin/setup-2fa"
  ) {
    return <Navigate to="/admin/setup-2fa" replace />;
  }
  return <>{children}</>;
}

function AccountError({ onRetry }: { onRetry: () => void }) {
  return (
    <main id="main" className="mx-auto max-w-lg px-4 py-24">
      <ErrorState
        title="We couldn’t check your account"
        description="DevSync didn’t answer just now. Try again in a moment; you’re still signed in."
        onRetry={onRetry}
      />
    </main>
  );
}

const AdminApp = lazy(() => import("@/features/admin/AdminApp"));

/** The admin bundle is requested only after the server confirms an admin session
 * with TOTP (`/admin/session` answers 404 to everyone else), spec §14.17. */
export function AdminArea() {
  const me = useMe();
  const check = useQuery({
    queryKey: ["admin-session"],
    enabled: me.data?.role === "ADMIN" && me.data.totp_verified,
    retry: false,
    queryFn: () => api<{ totp_verified: boolean }>("/admin/session"),
  });
  if (me.isPending || (check.isPending && check.fetchStatus !== "idle")) return <Loading />;
  if (me.isError && me.data === undefined)
    return <AccountError onRetry={() => void me.refetch()} />;
  if (!me.data || me.data.role !== "ADMIN")
    return <Navigate to={me.data ? roleHome(me.data.role, me.data.status) : "/login"} replace />;
  if (!me.data.totp_verified) return <Navigate to="/admin/setup-2fa" replace />;
  if (!check.data) return <Navigate to="/403" replace />;
  return (
    <Suspense fallback={<Loading />}>
      <AdminApp />
    </Suspense>
  );
}
