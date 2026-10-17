import { createBrowserRouter } from "react-router";
import { AdminArea, RequireAuth } from "./guards";
import { ForbiddenPage, NotFoundPage } from "./ErrorPages";

/** Routes are code-split per page (spec §13.7). */
export const router = createBrowserRouter([
  {
    path: "/",
    lazy: async () => ({ Component: (await import("@/features/home/HomePage")).default }),
  },
  {
    path: "/login",
    lazy: async () => ({ Component: (await import("@/features/auth/LoginPage")).default }),
  },
  {
    path: "/login/totp",
    lazy: async () => ({ Component: (await import("@/features/auth/TotpLoginPage")).default }),
  },
  {
    path: "/register",
    lazy: async () => ({ Component: (await import("@/features/auth/RegisterPage")).default }),
  },
  {
    path: "/verify",
    lazy: async () => ({ Component: (await import("@/features/auth/VerifyPage")).default }),
  },
  {
    path: "/verify-email",
    lazy: async () => ({ Component: (await import("@/features/auth/VerifyEmailPage")).default }),
  },
  {
    path: "/forgot-password",
    lazy: async () => ({ Component: (await import("@/features/auth/ForgotPasswordPage")).default }),
  },
  {
    path: "/reset-password",
    lazy: async () => ({ Component: (await import("@/features/auth/ResetPasswordPage")).default }),
  },
  {
    path: "/client",
    lazy: async () => {
      const { default: RoleHome } = await import("@/features/home/RoleHome");
      return {
        element: (
          <RequireAuth roles={["CLIENT"]}>
            <RoleHome kind="CLIENT" />
          </RequireAuth>
        ),
      };
    },
  },
  {
    path: "/dev",
    lazy: async () => {
      const { default: RoleHome } = await import("@/features/home/RoleHome");
      return {
        element: (
          <RequireAuth roles={["DEVELOPER"]}>
            <RoleHome kind="DEVELOPER" />
          </RequireAuth>
        ),
      };
    },
  },
  {
    path: "/settings",
    lazy: async () => {
      const { default: SettingsPage } = await import("@/features/account/SettingsPage");
      return {
        element: (
          <RequireAuth>
            <SettingsPage />
          </RequireAuth>
        ),
      };
    },
  },
  {
    path: "/admin/setup-2fa",
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
  { path: "/admin", element: <AdminArea /> },
  { path: "/403", element: <ForbiddenPage /> },
  { path: "*", element: <NotFoundPage /> },
]);
