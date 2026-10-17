/**
 * Routes (spec §13.4, §13.11, §15.5), code-split per page (§13.7). The root layout carries
 * the error boundary, titles, toasts and the offline banner. Signed-in areas share the
 * role shell; pages that later phases build open a placeholder instead of a 404.
 * Development-only tools (`/dev/ui-kit`, `/__stills`) are compiled out of production builds.
 */
import { lazy, Suspense } from "react";
import { createBrowserRouter, type RouteObject } from "react-router";
import { PageSkeleton } from "@/components/shell/PageSkeleton";
import {
  ComingSoonPage,
  ForbiddenPage,
  MaintenancePage,
  NotFoundPage,
  RouteError,
} from "./ErrorPages";
import { AdminArea, RequireAuth } from "./guards";
import { UPCOMING } from "./navigation";
import { Root } from "./Root";

// The signed-in shell (navigation, command palette, menus) loads only for signed-in routes.
const LazyRoleShell = lazy(async () => ({ default: (await import("./RoleShell")).RoleShell }));

function RoleShell() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <LazyRoleShell />
    </Suspense>
  );
}

const DEV_TOOLS = import.meta.env.DEV || import.meta.env.VITE_DEV_TOOLS === "1";

const auth: RouteObject[] = [
  {
    path: "login",
    handle: { title: "Sign in" },
    lazy: async () => ({ Component: (await import("@/features/auth/LoginPage")).default }),
  },
  {
    path: "login/totp",
    handle: { title: "Two-step sign-in" },
    lazy: async () => ({ Component: (await import("@/features/auth/TotpLoginPage")).default }),
  },
  {
    path: "register",
    handle: { title: "Create your account" },
    lazy: async () => ({ Component: (await import("@/features/auth/RegisterPage")).default }),
  },
  {
    path: "verify",
    handle: { title: "Verify your account" },
    lazy: async () => ({ Component: (await import("@/features/auth/VerifyPage")).default }),
  },
  {
    path: "verify-email",
    handle: { title: "Verify your email" },
    lazy: async () => ({ Component: (await import("@/features/auth/VerifyEmailPage")).default }),
  },
  {
    path: "forgot-password",
    handle: { title: "Reset your password" },
    lazy: async () => ({ Component: (await import("@/features/auth/ForgotPasswordPage")).default }),
  },
  {
    path: "reset-password",
    handle: { title: "Choose a new password" },
    lazy: async () => ({ Component: (await import("@/features/auth/ResetPasswordPage")).default }),
  },
];

const publicPages: RouteObject[] = [
  {
    index: true,
    lazy: async () => ({ Component: (await import("@/features/landing/LandingPage")).default }),
  },
  {
    path: "projects",
    handle: { title: "Browse projects" },
    lazy: async () => ({
      Component: (await import("@/features/public/PublicProjectsPage")).default,
    }),
  },
  {
    path: "privacy",
    handle: { title: "Privacy" },
    lazy: async () => ({ Component: (await import("@/features/legal/LegalPage")).PrivacyPage }),
  },
  {
    path: "terms",
    handle: { title: "Terms of use" },
    lazy: async () => ({ Component: (await import("@/features/legal/LegalPage")).TermsPage }),
  },
];

function upcoming(prefix: string): RouteObject[] {
  return UPCOMING.filter((item) => item.to.startsWith(prefix)).map((item) => ({
    path: item.to.slice(1),
    handle: { title: item.label },
    element: <ComingSoonPage title={item.label} phase={item.phase ?? 0} />,
  }));
}

const devTools: RouteObject[] = DEV_TOOLS
  ? [
      {
        path: "dev/ui-kit",
        handle: { title: "UI kit" },
        lazy: async () => ({ Component: (await import("@/features/devtools/UiKitPage")).default }),
      },
      {
        path: "__stills",
        handle: { title: "Stills" },
        lazy: async () => ({ Component: (await import("@/features/devtools/StillsPage")).default }),
      },
    ]
  : [];

export const routes: RouteObject[] = [
  {
    element: <Root />,
    errorElement: <RouteError />,
    children: [
      ...publicPages,
      ...auth,
      ...devTools,
      {
        element: (
          <RequireAuth roles={["DEVELOPER"]}>
            <RoleShell />
          </RequireAuth>
        ),
        children: [
          {
            path: "dev",
            handle: { title: "Dashboard" },
            lazy: async () => ({
              Component: (await import("@/features/home/DeveloperHome")).default,
            }),
          },
          ...upcoming("/dev/"),
        ],
      },
      {
        element: (
          <RequireAuth roles={["CLIENT"]}>
            <RoleShell />
          </RequireAuth>
        ),
        children: [
          {
            path: "client",
            handle: { title: "Dashboard" },
            lazy: async () => ({ Component: (await import("@/features/home/ClientHome")).default }),
          },
          ...upcoming("/client/"),
        ],
      },
      {
        element: (
          <RequireAuth>
            <RoleShell />
          </RequireAuth>
        ),
        children: [
          {
            path: "settings",
            handle: { title: "Settings" },
            lazy: async () => ({
              Component: (await import("@/features/account/SettingsPage")).default,
            }),
          },
          ...upcoming("/notifications"),
        ],
      },
      {
        path: "admin/setup-2fa",
        handle: { title: "Set up two-step sign-in" },
        lazy: async () => {
          const { default: Page } = await import("@/features/admin/SetupTwoFactorPage");
          return {
            element: (
              <RequireAuth roles={["ADMIN"]}>
                <Page />
              </RequireAuth>
            ),
          };
        },
      },
      { path: "admin/*", handle: { title: "Administration" }, element: <AdminArea /> },
      { path: "403", handle: { title: "Not allowed" }, element: <ForbiddenPage /> },
      { path: "maintenance", handle: { title: "Updating" }, element: <MaintenancePage /> },
      { path: "*", handle: { title: "Page not found" }, element: <NotFoundPage /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
