/** Admin navigation (spec §13.4). Lives in the admin chunk: other roles never download it. */
import {
  BadgeCheck,
  ChartPie,
  CreditCard,
  FileClock,
  Flag,
  FolderKanban,
  Gavel,
  House,
  Library,
  Medal,
  Settings,
  Siren,
  Users,
  Workflow,
} from "lucide-react";
import type { NavItem } from "@/app/navigation";
import type { ShellNav } from "@/components/shell/AppShell";

const sidebar: NavItem[] = [
  { label: "Dashboard", to: "/admin", icon: House },
  { label: "Users", to: "/admin/users", icon: Users, phase: 12 },
  { label: "Projects", to: "/admin/projects", icon: FolderKanban, phase: 12 },
  { label: "Team formation runs", to: "/admin/formation-runs", icon: Workflow, phase: 7 },
  { label: "Integrity flags", to: "/admin/flags", icon: Flag, phase: 11 },
  { label: "Platform alerts", to: "/admin/alerts", icon: Siren, phase: 12 },
  { label: "Disputes", to: "/admin/disputes", icon: Gavel, phase: 12 },
  { label: "Reputation", to: "/admin/reputation", icon: Medal, phase: 6 },
  { label: "Payments", to: "/admin/payments", icon: CreditCard, phase: 10 },
  { label: "Fairness analytics", to: "/admin/fairness", icon: ChartPie, phase: 12 },
  { label: "Content", to: "/admin/content", icon: Library, phase: 3 },
  { label: "Platform settings", to: "/admin/settings", icon: Settings, phase: 12 },
  { label: "Audit log", to: "/admin/audit", icon: FileClock, phase: 12 },
  { label: "My account", to: "/settings", icon: BadgeCheck },
];

function find(path: string, label?: string): NavItem {
  const item = sidebar.find((i) => i.to === path);
  if (!item) throw new Error(`admin navigation: unknown path ${path}`);
  return label ? { ...item, label } : item;
}

export const ADMIN_NAV: ShellNav = {
  home: "/admin",
  sidebar,
  tabs: [find("/admin", "Dashboard"), find("/admin/disputes"), find("/admin/flags", "Flags")],
  profilePath: "/settings",
};
