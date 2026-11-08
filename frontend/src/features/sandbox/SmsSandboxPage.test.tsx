import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/Toaster";
import { clearToasts } from "@/components/ui/toast-store";
import { renderRoutes } from "@/test/render";
import { server } from "@/test/server";
import { digitsOnly, type SandboxSmsList } from "./api";
import SmsSandboxPage from "./SmsSandboxPage";

const NOW = new Date().toISOString();
const LIST: SandboxSmsList = {
  newest_code: "333333",
  messages: [
    { id: "3", to: "+8801711111111", text: "Your DevSync code is 333333", code: "333333", at: NOW },
    { id: "2", to: "+8801722222222", text: "Your DevSync code is 222222", code: "222222", at: NOW },
    { id: "1", to: "+8801711111111", text: "Your DevSync code is 111111", code: "111111", at: NOW },
  ],
};

const inbox = (body: SandboxSmsList = LIST) =>
  http.get("*/api/v1/dev-sandbox/sms", () => HttpResponse.json(body));
const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });

function show() {
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
    ],
    "/sandbox/sms",
  );
}

afterEach(() => {
  clearToasts();
  vi.restoreAllMocks();
});

describe("SMS inbox page", () => {
  it("shows the newest code big and every text newest first", async () => {
    server.use(inbox());
    show();
    expect(await screen.findByTestId("newest-code")).toHaveTextContent("333333");
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0] as HTMLElement).getByText("+8801711111111")).toBeInTheDocument();
    expect(
      within(rows[2] as HTMLElement).getByText("Your DevSync code is 111111"),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "SMS inbox" })).toBeInTheDocument();
  });

  it("says what to do when no text has arrived yet", async () => {
    server.use(inbox({ messages: [], newest_code: null }));
    show();
    expect(await screen.findByText("No texts yet")).toBeInTheDocument();
    expect(screen.queryByTestId("newest-code")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear inbox" })).toBeDisabled();
  });

  it("filters by number, ignoring plus signs and spaces", async () => {
    server.use(inbox());
    show();
    await screen.findByTestId("newest-code");
    await userEvent.type(screen.getByLabelText("Show texts to"), "+880 17222");
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByTestId("newest-code")).toHaveTextContent("222222");
    await userEvent.clear(screen.getByLabelText("Show texts to"));
    await userEvent.type(screen.getByLabelText("Show texts to"), "999");
    expect(screen.getByText("No texts to that number")).toBeInTheDocument();
    expect(screen.queryByTestId("newest-code")).not.toBeInTheDocument();
  });

  it("copies a code and confirms it", async () => {
    server.use(inbox());
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    show();
    await screen.findByTestId("newest-code");
    await userEvent.click(
      screen.getAllByRole("button", { name: "Copy code 333333" })[0] as HTMLElement,
    );
    expect(writeText).toHaveBeenCalledWith("333333");
    expect(await screen.findByText("Code copied")).toBeInTheDocument();
  });

  it("tells you when copying isn't possible instead of failing silently", async () => {
    server.use(inbox());
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
      configurable: true,
    });
    show();
    await screen.findByTestId("newest-code");
    await userEvent.click(
      screen.getAllByRole("button", { name: "Copy code 333333" })[0] as HTMLElement,
    );
    expect(await screen.findByText("Couldn’t copy")).toBeInTheDocument();
  });

  it("clears the inbox", async () => {
    let cleared = false;
    server.use(
      csrf(),
      http.get("*/api/v1/dev-sandbox/sms", () =>
        HttpResponse.json(cleared ? { messages: [], newest_code: null } : LIST),
      ),
      http.delete("*/api/v1/dev-sandbox/sms", () => {
        cleared = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    show();
    await screen.findByTestId("newest-code");
    await userEvent.click(screen.getByRole("button", { name: "Clear inbox" }));
    expect(await screen.findByText("Inbox cleared")).toBeInTheDocument();
    expect(await screen.findByText("No texts yet")).toBeInTheDocument();
  });

  it("is explicit that the inbox is off where the server doesn't provide it", async () => {
    server.use(
      http.get("*/api/v1/dev-sandbox/sms", () =>
        HttpResponse.json({ error: { code: "NOT_FOUND", message: "Not found" } }, { status: 404 }),
      ),
    );
    show();
    expect(await screen.findByText("The SMS inbox is off here")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear inbox" })).toBeDisabled();
  });

  it("shows an error with Try again when the server fails", async () => {
    let failing = true;
    server.use(
      http.get("*/api/v1/dev-sandbox/sms", () =>
        failing
          ? HttpResponse.json({ error: { code: "INTERNAL", message: "Oops" } }, { status: 500 })
          : HttpResponse.json(LIST),
      ),
    );
    show();
    // One automatic retry comes first, so the error state follows after a short pause.
    expect(
      await screen.findByText("The inbox didn’t load", undefined, { timeout: 5000 }),
    ).toBeInTheDocument();
    failing = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("newest-code")).toHaveTextContent("333333");
  }, 10_000);

  it("picks up a new text by itself while live", async () => {
    let calls = 0;
    server.use(
      http.get("*/api/v1/dev-sandbox/sms", () => {
        calls += 1;
        return HttpResponse.json(calls === 1 ? { messages: [], newest_code: null } : LIST);
      }),
    );
    show();
    expect(await screen.findByText("No texts yet")).toBeInTheDocument();
    await waitFor(
      () => {
        expect(screen.getByTestId("newest-code")).toHaveTextContent("333333");
      },
      {
        timeout: 6000,
      },
    );
  }, 10_000);

  it("stops refreshing when live is switched off", async () => {
    let calls = 0;
    server.use(
      http.get("*/api/v1/dev-sandbox/sms", () => {
        calls += 1;
        return HttpResponse.json({ messages: [], newest_code: null });
      }),
    );
    show();
    await screen.findByText("No texts yet");
    await userEvent.click(screen.getByRole("switch", { name: /Refresh every few seconds/ }));
    const seen = calls;
    await new Promise((r) => setTimeout(r, 3500));
    expect(calls).toBe(seen);
  }, 10_000);
});

describe("digitsOnly", () => {
  it.each([
    ["+880 1712-345678", "8801712345678"],
    ["", ""],
    ["abc", ""],
    ["٣٤٥", ""],
  ])("%s → %s", (input, expected) => {
    expect(digitsOnly(input)).toBe(expected);
  });
});
