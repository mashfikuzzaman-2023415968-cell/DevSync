import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/AppShell";
import { ADMIN_NAV } from "./nav";

/** Admin navigation around shared pages (e.g. /settings) for a signed-in admin. */
export default function AdminShell({ children }: { children: ReactNode }) {
  return <AppShell nav={ADMIN_NAV}>{children}</AppShell>;
}
