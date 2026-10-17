import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useMe } from "@/features/auth/api";
import { roleHome } from "@/lib/redirects";

function Loading() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg" role="status">
      <span className="text-body text-text-muted">Loading…</span>
    </div>
  );
}

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
  if (!me.data) {
    const returnTo = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?return_to=${returnTo}`} replace />;
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

const AdminHome = lazy(() => import("@/features/admin/AdminHome"));

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
  if (!me.data || me.data.role !== "ADMIN")
    return <Navigate to={me.data ? roleHome(me.data.role, me.data.status) : "/login"} replace />;
  if (!me.data.totp_verified) return <Navigate to="/admin/setup-2fa" replace />;
  if (!check.data) return <Navigate to="/403" replace />;
  return (
    <Suspense fallback={<Loading />}>
      <AdminHome />
    </Suspense>
  );
}
