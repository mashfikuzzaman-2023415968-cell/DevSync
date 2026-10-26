/** "Session expired" / "Suspended" and the maintenance page (spec §13.4, §13.5 #8). */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Outlet } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, MAINTENANCE_EVENT } from "@/api/client";
import LoginPage from "@/features/auth/LoginPage";
import { pageLoad } from "@/lib/redirects";
import {
  clearSignedOutReason,
  parseReason,
  SIGNED_OUT_EVENT,
  signedOutReason,
} from "@/lib/sessionNotice";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import { AppEvents } from "./AppEvents";
import { MaintenancePage } from "./ErrorPages";
import { RequireAuth } from "./guards";

const API = "*/api/v1";
const ME = {
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
};
const ended = (code: string) =>
  HttpResponse.json({ error: { code, message: "ended" } }, { status: 401 });

afterEach(() => {
  clearSignedOutReason();
});

function shell() {
  return [
    {
      element: (
        <>
          <AppEvents />
          <Outlet />
        </>
      ),
      children: [
        {
          path: "/client/x",
          element: (
            <RequireAuth roles={["CLIENT"]}>
              <ProjectsProbe />
            </RequireAuth>
          ),
        },
        { path: "/login", element: <LoginPage /> },
        { path: "/maintenance", element: <MaintenancePage /> },
      ],
    },
  ];
}

function ProjectsProbe() {
  return (
    <>
      <Probe label="client page" />
      <button
        type="button"
        onClick={() => {
          void api("/projects").catch(() => undefined);
        }}
      >
        Load projects
      </button>
    </>
  );
}

describe("fetch wrapper announcements", () => {
  it("notes an expired or suspended session, but not the sign-in form's own answer", async () => {
    const events: string[] = [];
    const listener = (e: Event) => {
      events.push((e as CustomEvent<{ reason: string }>).detail.reason);
    };
    window.addEventListener(SIGNED_OUT_EVENT, listener);
    server.use(
      http.get(`${API}/a`, () => ended("SESSION_EXPIRED")),
      http.get(`${API}/b`, () => ended("ACCOUNT_SUSPENDED")),
      http.get(`${API}/c`, () => ended("UNAUTHENTICATED")),
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.post(`${API}/auth/login`, () => ended("ACCOUNT_SUSPENDED")),
    );
    try {
      await expect(api("/c")).rejects.toBeInstanceOf(ApiError);
      expect(signedOutReason()).toBeNull(); // a plain "please sign in" says nothing more
      await expect(api("/auth/login", { method: "POST", body: {} })).rejects.toMatchObject({
        code: "ACCOUNT_SUSPENDED",
      });
      expect(signedOutReason()).toBeNull();
      await expect(api("/a")).rejects.toMatchObject({ code: "SESSION_EXPIRED" });
      expect(signedOutReason()).toBe("session_expired");
      await expect(api("/b")).rejects.toMatchObject({ code: "ACCOUNT_SUSPENDED" });
      expect(signedOutReason()).toBe("account_suspended");
      // A parallel request's "expired" never hides a suspension.
      await expect(api("/a")).rejects.toMatchObject({ code: "SESSION_EXPIRED" });
      expect(signedOutReason()).toBe("account_suspended");
      expect(events).toEqual(["session_expired", "account_suspended", "session_expired"]);
    } finally {
      window.removeEventListener(SIGNED_OUT_EVENT, listener);
    }
  });

  it("announces a 503, even when the proxy answers with an HTML page", async () => {
    let fired = 0;
    const listener = () => {
      fired += 1;
    };
    window.addEventListener(MAINTENANCE_EVENT, listener);
    server.use(
      http.get(
        `${API}/down`,
        () => new HttpResponse("<html>Down for maintenance</html>", { status: 503 }),
      ),
      http.get(`${API}/broken`, () => HttpResponse.json({}, { status: 500 })),
    );
    try {
      await expect(api("/down")).rejects.toMatchObject({ status: 503 });
      await expect(api("/broken")).rejects.toMatchObject({ status: 500 });
      expect(fired).toBe(1);
    } finally {
      window.removeEventListener(MAINTENANCE_EVENT, listener);
    }
  });

  it("accepts only the two known reasons from the address bar", () => {
    expect(parseReason("session_expired")).toBe("session_expired");
    expect(parseReason("account_suspended")).toBe("account_suspended");
    expect(parseReason("<script>")).toBeNull();
    expect(parseReason("")).toBeNull();
    expect(parseReason(null)).toBeNull();
  });
});

describe("a session that ends while the app is open", () => {
  it("sends the person to sign in saying the session expired", async () => {
    let expired = false;
    server.use(
      http.get(`${API}/me`, () => (expired ? ended("UNAUTHENTICATED") : HttpResponse.json(ME))),
      http.get(`${API}/projects`, () => {
        expired = true;
        return ended("SESSION_EXPIRED");
      }),
    );
    const user = userEvent.setup();
    const { router } = renderRoutes(shell(), "/client/x");
    await user.click(await screen.findByRole("button", { name: "Load projects" }));
    expect(await screen.findByText("You’ve been signed out")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    const params = new URLSearchParams(router.state.location.search);
    expect(params.get("return_to")).toBe("/client/x");
    expect(params.get("reason")).toBe("session_expired");
    expect(signedOutReason()).toBeNull(); // shown once
  });

  it("says the account is suspended", async () => {
    server.use(http.get(`${API}/me`, () => ended("ACCOUNT_SUSPENDED")));
    renderRoutes(shell(), "/client/x");
    expect(await screen.findByText("This account is suspended")).toBeInTheDocument();
    expect(screen.getByText(/Contact support/)).toBeInTheDocument();
  });

  it("shows no notice for an unknown reason in the address", async () => {
    renderRoutes(shell(), "/login?reason=hacked");
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByText(/session expired|suspended/i)).not.toBeInTheDocument();
  });
});

describe("maintenance page on 503", () => {
  it("opens on a 503 and tries the same page again", async () => {
    server.use(
      http.get(`${API}/me`, () => HttpResponse.json(ME)),
      http.get(`${API}/projects`, () =>
        HttpResponse.json(
          { error: { code: "DEPENDENCY_UNAVAILABLE", message: "Unavailable." } },
          { status: 503 },
        ),
      ),
    );
    const to = vi.spyOn(pageLoad, "to").mockImplementation(() => undefined);
    try {
      const user = userEvent.setup();
      const { router } = renderRoutes(shell(), "/client/x?tab=2");
      await user.click(await screen.findByRole("button", { name: "Load projects" }));
      expect(await screen.findByText("DevSync is being updated")).toBeInTheDocument();
      expect(router.state.location.pathname).toBe("/maintenance");
      await user.click(screen.getByRole("button", { name: "Try again" }));
      expect(to).toHaveBeenCalledWith("/client/x?tab=2");
    } finally {
      to.mockRestore();
    }
  });

  it("never follows an unsafe return_to", async () => {
    const to = vi.spyOn(pageLoad, "to").mockImplementation(() => undefined);
    try {
      const user = userEvent.setup();
      renderRoutes(shell(), "/maintenance?return_to=%2F%2Fevil.example");
      await user.click(await screen.findByRole("button", { name: "Try again" }));
      await waitFor(() => {
        expect(to).toHaveBeenCalledWith("/");
      });
    } finally {
      to.mockRestore();
    }
  });
});
