/** Every screen built so far (spec §13.14 "every built screen"), used by the CSP, axe and
 * responsive-matrix checks. Screens that need an object id (a test attempt, a public profile)
 * are checked in phase3.spec.ts. `role` screens need a signed-in user of that role. */
export interface Screen {
  name: string;
  path: string;
  role?: "CLIENT" | "DEVELOPER" | "ADMIN";
}

export const PUBLIC_SCREENS: Screen[] = [
  { name: "homepage", path: "/" },
  { name: "login", path: "/login" },
  { name: "register", path: "/register" },
  { name: "register-details", path: "/register?role=developer" },
  { name: "forgot-password", path: "/forgot-password" },
  { name: "reset-password", path: "/reset-password?token=example" },
  { name: "projects", path: "/projects" },
  { name: "privacy", path: "/privacy" },
  { name: "terms", path: "/terms" },
  { name: "not-found", path: "/no/such/page" },
  { name: "forbidden", path: "/403" },
  { name: "maintenance", path: "/maintenance" },
];

export const SIGNED_IN_SCREENS: Screen[] = [
  { name: "developer-home", path: "/dev", role: "DEVELOPER" },
  { name: "find-work", path: "/dev/find", role: "DEVELOPER" },
  { name: "my-bids", path: "/dev/bids", role: "DEVELOPER" },
  { name: "developer-coming-soon", path: "/dev/projects", role: "DEVELOPER" },
  { name: "settings", path: "/settings", role: "DEVELOPER" },
  { name: "developer-profile", path: "/dev/profile", role: "DEVELOPER" },
  { name: "skill-challenges", path: "/dev/challenges", role: "DEVELOPER" },
  { name: "client-home", path: "/client", role: "CLIENT" },
  { name: "client-projects", path: "/client/projects", role: "CLIENT" },
  { name: "client-create-project", path: "/client/projects/new", role: "CLIENT" },
  { name: "client-settings", path: "/settings", role: "CLIENT" },
  { name: "admin-home", path: "/admin", role: "ADMIN" },
];
