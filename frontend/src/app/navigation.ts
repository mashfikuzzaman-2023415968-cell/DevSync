/**
 * Role navigation (spec §13.4, §13.14). Pages that later phases build are already listed,
 * so the shell is complete; until then they open a "coming in Phase N" page instead of a 404.
 * Admin navigation lives in the admin bundle (features/admin) so it never reaches other
 * roles (spec §14.17).
 */
import {
  Bell,
  BriefcaseBusiness,
  ChartColumn,
  CirclePlus,
  CreditCard,
  FolderKanban,
  Gavel,
  House,
  ListChecks,
  Medal,
  Search,
  Settings,
  UserRound,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Phase that builds the page; undefined when it exists now. */
  phase?: number;
  /** Words the command palette also matches. */
  keywords?: string[];
}

export interface RoleNav {
  home: string;
  sidebar: NavItem[];
  /** Bottom tab bar on phones: four destinations; "More" opens the rest (§13.14). */
  tabs: NavItem[];
}

const notifications: NavItem = {
  label: "Notifications",
  to: "/notifications",
  icon: Bell,
  phase: 8,
};
const settings: NavItem = {
  label: "Settings",
  to: "/settings",
  icon: Settings,
  keywords: ["password", "theme", "sessions"],
};

const developer: NavItem[] = [
  { label: "Dashboard", to: "/dev", icon: House },
  {
    label: "Find projects",
    to: "/dev/find",
    icon: Search,
    phase: 5,
    keywords: ["search", "work", "bid"],
  },
  { label: "My bids", to: "/dev/bids", icon: Gavel, phase: 5 },
  { label: "My projects", to: "/dev/projects", icon: FolderKanban, phase: 9 },
  {
    label: "Skill challenges",
    to: "/dev/challenges",
    icon: ListChecks,
    keywords: ["test", "quiz", "verified score"],
  },
  {
    label: "Profile & portfolio",
    to: "/dev/profile",
    icon: UserRound,
    keywords: ["skills", "certificates", "reviews"],
  },
  { label: "Reputation", to: "/dev/reputation", icon: Medal, phase: 6 },
  { label: "Earnings", to: "/dev/earnings", icon: Wallet, phase: 10 },
  notifications,
  settings,
];

const client: NavItem[] = [
  { label: "Dashboard", to: "/client", icon: House },
  {
    label: "Create project",
    to: "/client/projects/new",
    icon: CirclePlus,
    phase: 4,
    keywords: ["new", "plan"],
  },
  { label: "My projects", to: "/client/projects", icon: FolderKanban, phase: 4 },
  { label: "Teams", to: "/client/teams", icon: Users, phase: 7 },
  { label: "Payments", to: "/client/payments", icon: CreditCard, phase: 10, keywords: ["escrow"] },
  { label: "Disputes", to: "/client/disputes", icon: BriefcaseBusiness, phase: 12 },
  { label: "Analytics", to: "/client/analytics", icon: ChartColumn, phase: 11 },
  notifications,
  settings,
];

function one(items: NavItem[], path: string, label?: string): NavItem {
  const item = items.find((i) => i.to === path);
  if (!item) throw new Error(`navigation: unknown path ${path}`);
  return label ? { ...item, label } : item;
}

export const NAV: Record<"CLIENT" | "DEVELOPER", RoleNav> = {
  DEVELOPER: {
    home: "/dev",
    sidebar: developer,
    tabs: [
      one(developer, "/dev", "Home"),
      one(developer, "/dev/find", "Find work"),
      one(developer, "/dev/projects"),
    ],
  },
  CLIENT: {
    home: "/client",
    sidebar: client,
    tabs: [
      one(client, "/client", "Home"),
      one(client, "/client/projects", "Projects"),
      one(client, "/client/payments"),
    ],
  },
};

/** Every not-yet-built page across roles, for the router's placeholder routes. */
export const UPCOMING: NavItem[] = [...developer, ...client].filter(
  (item, i, all) => item.phase !== undefined && all.findIndex((x) => x.to === item.to) === i,
);
