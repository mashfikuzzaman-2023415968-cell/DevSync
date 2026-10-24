/** Settings screen (spec §13.5 #19): name, appearance, devices and change password —
 * including what each card does when the server refuses. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, type JsonBodyType } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PreferencesProvider } from "@/design/preferences";
import { renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import SettingsPage from "./SettingsPage";

const ME = {
  id: "u1",
  email: "rahim@example.com",
  phone_e164: "+8801712345678",
  display_name: "Rahim Uddin",
  role: "DEVELOPER",
  status: "ACTIVE",
  email_verified: true,
  phone_verified: true,
  payment_verified: false,
  totp_enabled: false,
  totp_verified: false,
  created_at: "2026-10-01T00:00:00Z",
};

const SESSIONS = {
  items: [
    {
      id: "s1",
      current: true,
      ip: "203.0.113.5",
      user_agent: "Firefox on Linux",
      created_at: "2026-10-20T04:00:00Z",
      last_seen_at: "2026-10-24T04:00:00Z",
    },
    {
      id: "s2",
      current: false,
      ip: "203.0.113.9",
      user_agent: "Safari on iPhone",
      created_at: "2026-10-18T04:00:00Z",
      last_seen_at: "2026-10-23T04:00:00Z",
    },
  ],
};

function error(code: string, fields?: Record<string, string>): JsonBodyType {
  return { error: { code, message: "Some fields need attention.", fields, request_id: "req_1" } };
}

function render(...handlers: Parameters<typeof server.use>) {
  // The first matching handler wins, so a test's own handlers come before the defaults.
  server.use(
    ...handlers,
    http.get("*/api/v1/auth/csrf", () => new HttpResponse(null, { status: 204 })),
    http.get("*/api/v1/me", () => HttpResponse.json(ME)),
    http.get("*/api/v1/auth/sessions", () => HttpResponse.json(SESSIONS)),
  );
  return renderRoutes(
    [
      {
        path: "/settings",
        element: (
          <PreferencesProvider>
            <SettingsPage />
          </PreferencesProvider>
        ),
      },
    ],
    "/settings",
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("shows the account, appearance, devices and password cards", async () => {
    render();
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("Rahim Uddin")).toBeInTheDocument();
    expect(screen.getByText("rahim@example.com")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Appearance" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Change password" })).toBeInTheDocument();
    // A developer gets no organisation card (clients do).
    expect(screen.queryByText("Organisation")).not.toBeInTheDocument();
  });

  it("saves the name and shows the server's field error", async () => {
    const user = userEvent.setup();
    let sent: unknown = null;
    render(
      http.patch("*/api/v1/me", async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json(error("VALIDATION_ERROR", { display_name: "Too short." }), {
          status: 422,
        });
      }),
    );
    const field = await screen.findByDisplayValue("Rahim Uddin");
    await user.clear(field);
    await user.type(field, "R");
    await user.click(screen.getByRole("button", { name: "Save name" }));
    expect((await screen.findAllByText("Too short.")).length).toBeGreaterThan(0);
    expect(sent).toEqual({ display_name: "R" });
  });

  it("remembers the theme on this device", async () => {
    const user = userEvent.setup();
    render();
    await user.click(await screen.findByRole("radio", { name: "Dark" }));
    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("dark");
    });
  });

  it("lists devices, marks this one and signs another out", async () => {
    const user = userEvent.setup();
    const revoked: string[] = [];
    render(
      http.delete("*/api/v1/auth/sessions/:id", ({ params }) => {
        revoked.push(String(params.id));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const list = (await screen.findByText("Firefox on Linux")).closest("ul");
    expect(list).not.toBeNull();
    const rows = within(list as HTMLElement).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    const [thisDevice, other] = rows as [HTMLElement, HTMLElement];
    expect(thisDevice).toHaveTextContent("This device");
    // Only the other device can be signed out.
    expect(within(thisDevice).queryByRole("button", { name: "Sign out" })).toBeNull();
    await user.click(within(other).getByRole("button", { name: "Sign out" }));
    await waitFor(() => {
      expect(revoked).toEqual(["s2"]);
    });
  });

  it("keeps a device that the server refused to sign out", async () => {
    const user = userEvent.setup();
    render(
      http.delete("*/api/v1/auth/sessions/:id", () =>
        HttpResponse.json(error("NOT_FOUND"), { status: 404 }),
      ),
    );
    await screen.findByText("Safari on iPhone");
    const row = screen.getByText("Safari on iPhone").closest("li") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "Sign out" }));
    // The refusal is reported as a toast; the device is never removed on a failure.
    await waitFor(() => {
      expect(within(row).getByRole("button", { name: "Sign out" })).toBeEnabled();
    });
    expect(screen.getByText("Safari on iPhone")).toBeInTheDocument();
  });

  it("changes the password and says the other devices were signed out", async () => {
    const user = userEvent.setup();
    render(
      http.post("*/api/v1/auth/password/change", () => new HttpResponse(null, { status: 204 })),
    );
    await user.type(await screen.findByLabelText("Current password"), "correct horse battery 42!");
    await user.type(screen.getByLabelText("New password"), "another strong phrase 31!");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(
      await screen.findByText("Password changed. Your other devices were signed out."),
    ).toBeInTheDocument();
  });

  it("shows the server's reason when the current password is wrong", async () => {
    const user = userEvent.setup();
    render(
      http.post("*/api/v1/auth/password/change", () =>
        HttpResponse.json(
          error("VALIDATION_ERROR", { current_password: "That isn’t your current password." }),
          {
            status: 422,
          },
        ),
      ),
    );
    await user.type(await screen.findByLabelText("Current password"), "wrong phrase 99!");
    await user.type(screen.getByLabelText("New password"), "another strong phrase 31!");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("That isn’t your current password.")).toBeInTheDocument();
  });

  it("offers to sign out of every device and asks first", async () => {
    const user = userEvent.setup();
    const logout = vi.fn(() => new HttpResponse(null, { status: 204 }));
    render(http.post("*/api/v1/auth/logout-all", logout));
    await user.click(await screen.findByRole("button", { name: /Sign out of every device/ }));
    expect(await screen.findByText("Sign out of every device?")).toBeInTheDocument();
    expect(logout).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Sign out everywhere" }));
    await waitFor(() => {
      expect(logout).toHaveBeenCalled();
    });
  });

  it("offers to try again when the device list fails", async () => {
    let calls = 0;
    render(
      http.get("*/api/v1/auth/sessions", () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(error("INTERNAL"), { status: 500 })
          : HttpResponse.json(SESSIONS);
      }),
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Try again/i }, { timeout: 3000 }));
    expect(await screen.findByText("Firefox on Linux")).toBeInTheDocument();
  });
});
