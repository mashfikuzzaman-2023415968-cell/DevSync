import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import SettingsPage from "@/features/account/SettingsPage";
import SetupTwoFactorPage from "@/features/admin/SetupTwoFactorPage";
import HomePage from "@/features/home/HomePage";
import RoleHome from "@/features/home/RoleHome";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import ForgotPasswordPage from "./ForgotPasswordPage";
import ResetPasswordPage from "./ResetPasswordPage";
import TotpLoginPage from "./TotpLoginPage";
import VerifyEmailPage from "./VerifyEmailPage";
import VerifyPage from "./VerifyPage";

const ME = {
  id: "u1",
  email: "nadia@example.com",
  phone_e164: "+8801712345678",
  display_name: "Nadia",
  role: "DEVELOPER",
  status: "PENDING",
  email_verified: false,
  phone_verified: false,
  totp_enabled: false,
  totp_verified: false,
  created_at: "2026-10-17T00:00:00Z",
};

const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });
const me = (over: Partial<typeof ME> = {}) =>
  http.get("*/api/v1/me", () => HttpResponse.json({ ...ME, ...over }));
const challenge = () =>
  http.get("*/api/v1/captcha/challenge", () =>
    // sha256("s0") so n = 0 solves it immediately
    HttpResponse.json({
      algorithm: "SHA-256",
      challenge: "ec18eac8d758b1eba52d3c10d39adc6dd9806472cb4ae069635d383d9086a513",
      max_number: 0,
      salt: "s",
      signature: "g",
    }),
  );

describe("VerifyPage", () => {
  it("verifies the phone and offers a fresh email link", async () => {
    let verified = false;
    server.use(
      csrf(),
      http.get("*/api/v1/me", () => HttpResponse.json({ ...ME, phone_verified: verified })),
      http.post("*/api/v1/auth/otp/verify", async ({ request }) => {
        const body = (await request.json()) as { code: string };
        verified = body.code === "123456";
        return verified
          ? new HttpResponse(null, { status: 204 })
          : HttpResponse.json(
              {
                error: {
                  code: "TOKEN_INVALID",
                  message: "This link or code is invalid or has expired.",
                },
              },
              { status: 400 },
            );
      }),
      http.post("*/api/v1/auth/email/resend", () => new HttpResponse(null, { status: 204 })),
    );
    renderRoutes([{ path: "/verify", element: <VerifyPage /> }], "/verify");
    const user = userEvent.setup();
    expect(
      await screen.findByText(/Enter the code we sent to \+8801712345678/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Send a new code in/ })).toBeDisabled();
    await user.keyboard("999999");
    await user.click(screen.getByRole("button", { name: "Verify phone" }));
    expect(await screen.findByText(/invalid or has expired/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send a new link" }));
    expect(await screen.findByText(/We sent a new link/)).toBeInTheDocument();
  });

  it("redirects active users home and signed-out users to login", async () => {
    server.use(me({ status: "ACTIVE" }));
    renderRoutes(
      [
        { path: "/verify", element: <VerifyPage /> },
        { path: "/dev", element: <Probe label="dev home" /> },
      ],
      "/verify",
    );
    expect(await screen.findByText("dev home")).toBeInTheDocument();
  });
});

describe("TotpLoginPage", () => {
  it("bounces to login without a pending sign-in", async () => {
    renderRoutes(
      [
        { path: "/login/totp", element: <TotpLoginPage /> },
        { path: "/login", element: <Probe label="login" /> },
      ],
      "/login/totp",
    );
    expect(await screen.findByText("login")).toBeInTheDocument();
  });
});

describe("Forgot and reset password", () => {
  it("shows the uniform confirmation", async () => {
    server.use(
      csrf(),
      challenge(),
      http.post("*/api/v1/auth/password/forgot", () =>
        HttpResponse.json(
          { message: "If an account exists for that email, we've sent a reset link." },
          { status: 202 },
        ),
      ),
    );
    renderRoutes(
      [{ path: "/forgot-password", element: <ForgotPasswordPage /> }],
      "/forgot-password",
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "nadia@example.com");
    await user.click(screen.getByRole("button", { name: "Email me a reset link" }));
    expect(await screen.findByText(/If an account exists/)).toBeInTheDocument();
  });

  it("sets a new password from the link", async () => {
    let body: unknown = null;
    server.use(
      csrf(),
      http.post("*/api/v1/auth/password/reset", async ({ request }) => {
        body = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderRoutes(
      [{ path: "/reset-password", element: <ResetPasswordPage /> }],
      "/reset-password?token=abc123",
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("New password"), "a fresh passphrase 9");
    await user.type(screen.getByLabelText("Repeat new password"), "a fresh passphrase 9");
    await user.click(screen.getByRole("button", { name: "Save new password" }));
    expect(await screen.findByText(/Your password is changed/)).toBeInTheDocument();
    expect(body).toEqual({ token: "abc123", new_password: "a fresh passphrase 9" });
  });
});

describe("VerifyEmailPage", () => {
  it("confirms the token once", async () => {
    let calls = 0;
    server.use(
      csrf(),
      http.post("*/api/v1/auth/email/verify", () => {
        calls += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderRoutes(
      [{ path: "/verify-email", element: <VerifyEmailPage /> }],
      "/verify-email?token=t0k3n",
    );
    expect(await screen.findByText("Your email is verified.")).toBeInTheDocument();
    expect(calls).toBe(1);
  });

  it("explains an incomplete link", () => {
    renderRoutes([{ path: "/verify-email", element: <VerifyEmailPage /> }], "/verify-email");
    expect(screen.getByText(/link is incomplete/)).toBeInTheDocument();
  });
});

describe("Signed-in pages", () => {
  it("home redirects signed-in users and shows calls to action to guests", async () => {
    server.use(
      http.get("*/api/v1/me", () =>
        HttpResponse.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 }),
      ),
    );
    renderRoutes([{ path: "/", element: <HomePage /> }], "/");
    expect(await screen.findByRole("link", { name: "Hire a team" })).toHaveAttribute(
      "href",
      "/register?role=client",
    );
    expect(screen.getByRole("link", { name: "Find work" })).toHaveAttribute(
      "href",
      "/register?role=developer",
    );
  });

  it("role home greets the user and signs out to the homepage", async () => {
    server.use(
      csrf(),
      me({ status: "ACTIVE" }),
      http.post("*/api/v1/auth/logout", () => new HttpResponse(null, { status: 204 })),
    );
    renderRoutes(
      [
        { path: "/dev", element: <RoleHome kind="DEVELOPER" /> },
        { path: "/", element: <Probe label="homepage" /> },
      ],
      "/dev",
    );
    expect(await screen.findByRole("heading", { name: "Hello, Nadia" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByText("homepage")).toBeInTheDocument();
  });

  it("settings lists devices, revokes one and changes the password", async () => {
    let revoked: string | null = null;
    server.use(
      csrf(),
      me({ status: "ACTIVE" }),
      http.get("*/api/v1/auth/sessions", () =>
        HttpResponse.json({
          items: [
            {
              id: "s1",
              current: true,
              ip: "203.0.113.1",
              user_agent: "Firefox",
              created_at: "2026-10-17T00:00:00Z",
              last_seen_at: "2026-10-17T00:00:00Z",
            },
            {
              id: "s2",
              current: false,
              ip: null,
              user_agent: "Phone",
              created_at: "2026-10-16T00:00:00Z",
              last_seen_at: "2026-10-16T08:00:00Z",
            },
          ],
        }),
      ),
      http.delete("*/api/v1/auth/sessions/:id", ({ params }) => {
        revoked = String(params.id);
        return new HttpResponse(null, { status: 204 });
      }),
      http.post("*/api/v1/auth/password/change", () =>
        HttpResponse.json(
          { error: { code: "INVALID_CREDENTIALS", message: "Email or password is incorrect." } },
          { status: 401 },
        ),
      ),
    );
    renderRoutes([{ path: "/settings", element: <SettingsPage /> }], "/settings");
    const user = userEvent.setup();
    expect(await screen.findByText("This device, 203.0.113.1")).toBeInTheDocument();
    const phoneRow = screen.getByText("Phone").closest("li") as HTMLElement;
    await user.click(within(phoneRow).getByRole("button", { name: "Sign out" }));
    await waitFor(() => {
      expect(revoked).toBe("s2");
    });
    await user.type(screen.getByLabelText("Current password"), "wrong one 12345");
    await user.type(screen.getByLabelText("New password"), "another phrase 31!");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("Email or password is incorrect.")).toBeInTheDocument();
  });

  it("admin 2FA setup shows the key, confirms and lists recovery codes", async () => {
    server.use(
      csrf(),
      me({ role: "ADMIN", status: "ACTIVE" }),
      http.post("*/api/v1/auth/totp/setup", () =>
        HttpResponse.json({ provisioning_uri: "otpauth://totp/x", secret: "JBSWY3DPEHPK3PXP" }),
      ),
      http.post("*/api/v1/auth/totp/confirm", () =>
        HttpResponse.json({ recovery_codes: ["aaaa-bbbb-cc", "dddd-eeee-ff"] }),
      ),
    );
    renderRoutes(
      [{ path: "/admin/setup-2fa", element: <SetupTwoFactorPage /> }],
      "/admin/setup-2fa",
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Create my authenticator key" }));
    expect(await screen.findByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
    await user.click(screen.getAllByRole("textbox")[0] as HTMLElement);
    await user.keyboard("123456");
    await user.click(screen.getByRole("button", { name: "Turn on two-step verification" }));
    expect(await screen.findByText("aaaa-bbbb-cc")).toBeInTheDocument();
  });
});
