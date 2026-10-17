/** Admin area (separate chunk, spec §14.17): shell with admin navigation and its pages.
 * Loaded only after the server confirms an admin session with TOTP. */
import { Route, Routes } from "react-router";
import { ComingSoonPage } from "@/app/ErrorPages";
import { NotFoundPage } from "@/app/ErrorPages";
import { AppShell } from "@/components/shell/AppShell";
import AdminHome from "./AdminHome";
import { ADMIN_NAV } from "./nav";

export default function AdminApp() {
  return (
    <AppShell nav={ADMIN_NAV}>
      <Routes>
        <Route index element={<AdminHome />} />
        {ADMIN_NAV.sidebar
          .filter((item) => item.phase !== undefined && item.to.startsWith("/admin/"))
          .map((item) => (
            <Route
              key={item.to}
              path={item.to.slice("/admin/".length)}
              element={<ComingSoonPage title={item.label} phase={item.phase ?? 0} />}
            />
          ))}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  );
}
