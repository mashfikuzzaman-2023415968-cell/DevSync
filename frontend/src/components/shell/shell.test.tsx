import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NAV } from "@/app/navigation";
import { pageLoad } from "@/lib/redirects";
import { server } from "@/test/server";
import { Probe, renderRoutes } from "@/test/render";
import { AppShell } from "./AppShell";
import { OfflineBanner } from "./OfflineBanner";
import { NETWORK_EVENT } from "@/api/client";
import { render, act } from "@testing-library/react";

const ME = {
  id: "u-1",
  email: "nadia@example.com",
  phone_e164: "+8801712345678",
  display_name: "Nadia Rahman",
  role: "DEVELOPER",
  status: "ACTIVE",
  email_verified: true,
  phone_verified: true,
  totp_enabled: false,
  totp_verified: false,
  created_at: "2026-10-17T00:00:00Z",
};

function shell(path = "/dev") {
  server.use(http.get("*/api/v1/me", () => HttpResponse.json(ME)));
  return renderRoutes(
    [
      {
        element: <AppShell nav={{ ...NAV.DEVELOPER, profilePath: "/dev/profile" }} />,
        children: [
          { path: "/dev", element: <Probe label="dev home" /> },
          { path: "/settings", element: <Probe label="settings page" /> },
          { path: "/dev/find", element: <Probe label="find page" /> },
        ],
      },
      { path: "/", element: <Probe label="homepage" /> },
    ],
    path,
  );
}

afterEach(() => {
  window.localStorage.clear();
});

describe("AppShell (spec §13.4)", () => {
  it("lists the role navigation and marks the current page", async () => {
    shell();
    const nav = await screen.findByRole("complementary", { name: "Main navigation" });
    const current = within(nav).getByRole("link", { name: "Dashboard" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(within(nav).getAllByRole("link")).toHaveLength(NAV.DEVELOPER.sidebar.length);
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
  });

  it("remembers the collapsed sidebar per user", async () => {
    const user = userEvent.setup();
    const first = shell();
    await user.click(await screen.findByRole("button", { name: "Collapse sidebar" }));
    expect(window.localStorage.getItem("ds-sidebar:u-1")).toBe("collapsed");
    first.unmount();
    shell();
    expect(await screen.findByRole("button", { name: "Expand sidebar" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("opens the command palette with Ctrl+K and navigates", async () => {
    const user = userEvent.setup();
    shell();
    await screen.findByText("dev home");
    await user.keyboard("{Control>}k{/Control}");
    const input = await screen.findByPlaceholderText("Go to a page or run an action…");
    await user.type(input, "settings");
    await user.keyboard("{Enter}");
    expect(await screen.findByText("settings page")).toBeInTheDocument();
  });

  it("has a bottom tab bar and a More sheet with the rest of the menu", async () => {
    const user = userEvent.setup();
    shell();
    const tabs = await screen.findByRole("navigation", { name: "Quick navigation" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((a) => a.textContent),
    ).toEqual(["Home", "Find work", "My projects"]);
    await user.click(within(tabs).getByRole("button", { name: "More" }));
    const sheet = await screen.findByRole("dialog", { name: "More" });
    expect(within(sheet).getByRole("link", { name: "Reputation" })).toBeInTheDocument();
    expect(within(sheet).queryByRole("link", { name: "Find projects" })).not.toBeInTheDocument();
  });

  it.each([
    ["signs out", 204],
    ["still leaves when the sign-out request fails", 500],
  ])("%s from the account menu with a fresh load of the homepage", async (_name, status) => {
    const to = vi.spyOn(pageLoad, "to").mockImplementation(() => undefined);
    let posted = false;
    server.use(
      http.get("*/api/v1/auth/csrf", () => {
        document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
        return new HttpResponse(null, { status: 204 });
      }),
      http.post("*/api/v1/auth/logout", () => {
        posted = true;
        return new HttpResponse(null, { status });
      }),
    );
    const user = userEvent.setup();
    shell();
    await user.click(await screen.findByRole("button", { name: "Account menu" }));
    await user.click(await screen.findByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => {
      expect(to).toHaveBeenCalledWith("/");
    });
    expect(posted).toBe(true);
    to.mockRestore();
  });
});

describe("OfflineBanner", () => {
  it("appears on network failure and hides after a successful request", async () => {
    render(<OfflineBanner />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new CustomEvent(NETWORK_EVENT, { detail: { online: false } }));
    });
    expect(screen.getByRole("status")).toHaveTextContent("You’re offline");
    act(() => {
      window.dispatchEvent(new CustomEvent(NETWORK_EVENT, { detail: { online: true } }));
    });
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });
});
