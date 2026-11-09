import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/Toaster";
import { clearToasts } from "@/components/ui/toast-store";
import { pageLoad } from "@/lib/redirects";
import { renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import SmsSandboxPage from "./SmsSandboxPage";

const ACCOUNTS = {
  accounts: [
    { email: "rahim@devsync.local", name: "Rahim (Rahim's Kitchen)", role: "CLIENT" },
    { email: "farzana@devsync.local", name: "Farzana (Studio Nokshi)", role: "CLIENT" },
    { email: "nusrat@devsync.local", name: "Nusrat Jahan", role: "DEVELOPER" },
    { email: "rafsan@devsync.local", name: "Rafsan Haque", role: "DEVELOPER" },
    { email: "tanvir@devsync.local", name: "Tanvir Ahmed", role: "DEVELOPER" },
  ],
};

const accounts = (body: Record<string, unknown> = ACCOUNTS, status = 200) =>
  http.get("*/api/v1/dev-sandbox/accounts", () => HttpResponse.json(body, { status }));
const emptyInbox = () =>
  http.get("*/api/v1/dev-sandbox/sms", () =>
    HttpResponse.json({ messages: [], newest_code: null }),
  );
const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });

function show(path = "/sandbox/sms?tab=signin") {
  return renderRoutes(
    [
      {
        path: "/sandbox/sms",
        element: (
          <>
            <SmsSandboxPage />
            <Toaster />
          </>
        ),
      },
      { path: "/login", element: <p>Sign in page</p> },
    ],
    path,
  );
}

afterEach(() => {
  clearToasts();
  vi.restoreAllMocks();
});

describe("Quick sign-in tab", () => {
  it("lists the demo people in walkthrough order, then the rest", async () => {
    server.use(accounts(), emptyInbox());
    show();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Quick sign-in" }),
    ).toBeInTheDocument();
    const names = (await screen.findAllByRole("listitem")).map((li) => li.textContent);
    expect(names[0]).toContain("Rahim");
    expect(names[1]).toContain("Nusrat");
    expect(names[2]).toContain("Rafsan");
    expect(names[3]).toContain("Farzana");
    expect(screen.getByText("Newcomer: takes the role assessment live")).toBeInTheDocument();
    // Not in the walkthrough list, so under "More accounts".
    expect(screen.getByText("More accounts")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in as Tanvir Ahmed" })).toBeInTheDocument();
  });

  it("signs in with one click and goes to that person's home", async () => {
    const assign = vi.spyOn(pageLoad, "to").mockImplementation(() => undefined);
    let posted: unknown = null;
    server.use(
      csrf(),
      accounts(),
      emptyInbox(),
      http.post("*/api/v1/dev-sandbox/sign-in", async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json({ redirect_to: "/dev" });
      }),
    );
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Sign in as Rafsan Haque" }));
    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith("/dev");
    });
    expect(posted).toEqual({ email: "rafsan@devsync.local" });
  });

  it("says so when the server refuses, and stays on the page", async () => {
    const assign = vi.spyOn(pageLoad, "to").mockImplementation(() => undefined);
    server.use(
      csrf(),
      accounts(),
      emptyInbox(),
      http.post("*/api/v1/dev-sandbox/sign-in", () =>
        HttpResponse.json(
          { error: { code: "INVALID_CREDENTIALS", message: "no" } },
          { status: 401 },
        ),
      ),
    );
    show();
    await userEvent.click(
      await screen.findByRole("button", { name: "Sign in as Rahim (Rahim's Kitchen)" }),
    );
    expect(await screen.findByText("Couldn’t sign in")).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });

  it("explains that the administrator has no shortcut", async () => {
    server.use(accounts(), emptyInbox());
    show();
    await screen.findByText("The demo");
    expect(screen.getByText(/administrator needs a code/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "normal sign-in page" })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("is explicit that it is off where the server doesn't provide it", async () => {
    server.use(accounts({ error: { code: "NOT_FOUND", message: "Not found" } }, 404), emptyInbox());
    show();
    expect(await screen.findByText("Quick sign-in is off here")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sign in as/ })).not.toBeInTheDocument();
  });

  it("asks to load the seed when there are no demo accounts", async () => {
    server.use(accounts({ accounts: [] }), emptyInbox());
    show();
    expect(await screen.findByText("No demo accounts yet")).toBeInTheDocument();
  });

  it("switches between the two tabs and keeps the SMS tab as the default", async () => {
    server.use(accounts(), emptyInbox());
    show("/sandbox/sms");
    expect(await screen.findByRole("heading", { level: 1, name: "SMS inbox" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Quick sign-in" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Quick sign-in" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "SMS inbox" }));
    expect(await screen.findByRole("heading", { level: 1, name: "SMS inbox" })).toBeInTheDocument();
  });
});
