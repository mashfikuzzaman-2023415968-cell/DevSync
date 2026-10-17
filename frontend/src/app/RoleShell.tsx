/** Picks the shell for the signed-in role. The admin shell comes from the admin chunk,
 * which only admins with a verified session download (spec §14.17). */
import { lazy, Suspense } from "react";
import { Outlet } from "react-router";
import { AppShell } from "@/components/shell/AppShell";
import { useMe } from "@/features/auth/api";
import { NAV } from "./navigation";

const AdminShell = lazy(() => import("@/features/admin/AdminShell"));

export function RoleShell() {
  const me = useMe();
  const role = me.data?.role;
  if (role === "ADMIN") {
    return (
      <Suspense fallback={null}>
        <AdminShell>
          <Outlet />
        </AdminShell>
      </Suspense>
    );
  }
  const nav = role === "CLIENT" ? NAV.CLIENT : NAV.DEVELOPER;
  return (
    <AppShell nav={{ ...nav, profilePath: role === "DEVELOPER" ? "/dev/profile" : "/settings" }} />
  );
}
