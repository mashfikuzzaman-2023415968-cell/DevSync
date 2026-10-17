import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import { AdminArea, RequireAuth } from "./guards";

const me = (over: Record<string, unknown>) =>
  http.get("*/api/v1/me", () =>
    HttpResponse.json({
      id: "u1",
      email: "a@b.co",
      phone_e164: null,
      display_name: "A",
      role: "CLIENT",
      status: "ACTIVE",
      email_verified: true,
      phone_verified: true,
      totp_enabled: false,
      totp_verified: false,
      created_at: "2026-10-17T00:00:00Z",
      ...over,
    }),
  );

const routes = [
  {
    path: "/client/x",
    element: (
      <RequireAuth roles={["CLIENT"]}>
        <Probe label="client page" />
      </RequireAuth>
    ),
  },
  { path: "/login", element: <Probe label="login page" /> },
  { path: "/verify", element: <Probe label="verify page" /> },
  { path: "/403", element: <Probe label="forbidden page" /> },
  { path: "/admin/setup-2fa", element: <Probe label="setup page" /> },
  { path: "/admin", element: <AdminArea /> },
  { path: "/client", element: <Probe label="client home" /> },
];

describe("route guards", () => {
  it("sends signed-out users to login with return_to", async () => {
    server.use(
      http.get("*/api/v1/me", () =>
        HttpResponse.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 }),
      ),
    );
    const { router } = renderRoutes(routes, "/client/x?tab=1");
    expect(await screen.findByText("login page")).toBeInTheDocument();
    expect(router.state.location.search).toBe("?return_to=%2Fclient%2Fx%3Ftab%3D1");
  });

  it("lets the right role through", async () => {
    server.use(me({}));
    renderRoutes(routes, "/client/x");
    expect(await screen.findByText("client page")).toBeInTheDocument();
  });

  it("sends pending users to verification", async () => {
    server.use(me({ status: "PENDING" }));
    renderRoutes(routes, "/client/x");
    expect(await screen.findByText("verify page")).toBeInTheDocument();
  });

  it("sends the wrong role to 403", async () => {
    server.use(me({ role: "DEVELOPER" }));
    renderRoutes(routes, "/client/x");
    expect(await screen.findByText("forbidden page")).toBeInTheDocument();
  });

  it("forces admins without TOTP to set it up and never loads the admin chunk for others", async () => {
    server.use(me({ role: "ADMIN", totp_verified: false }));
    renderRoutes(routes, "/admin");
    expect(await screen.findByText("setup page")).toBeInTheDocument();
  });

  it("redirects non-admins away from /admin", async () => {
    server.use(me({ role: "CLIENT" }));
    renderRoutes(routes, "/admin");
    expect(await screen.findByText("client home")).toBeInTheDocument();
  });

  it("loads the admin area after the server confirms the admin session", async () => {
    server.use(
      me({ role: "ADMIN", totp_verified: true, display_name: "Admin" }),
      http.get("*/api/v1/admin/session", () =>
        HttpResponse.json({ user_id: "u1", totp_verified: true, step_up_active: false }),
      ),
    );
    renderRoutes(routes, "/admin");
    expect(await screen.findByRole("heading", { name: "Administration" })).toBeInTheDocument();
  });
});
