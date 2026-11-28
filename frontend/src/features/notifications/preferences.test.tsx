/** Notification switches (screen 19; D153, D162) and the live stream hook (D153): every §12 row
 * with its in-app switch and, only where §12 has one, its email switch; a change saves one row at
 * once and moves back with the reason when refused; loading and error states. The stream: it
 * opens only when signed in, re-reads the list on each event, and after the browser gives up it
 * tries again after the first backoff pause; closing the page closes it. */
import { act, render, renderHook, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NotificationPreferences } from "@/api/types";
import { Toaster } from "@/components/ui/Toaster";
import { server } from "@/test/server";
import { STREAM_BACKOFF, useNotificationStream } from "./api";
import { NotificationPreferencesCard } from "./NotificationPreferencesCard";

const PREFS: NotificationPreferences = {
  items: [
    { category: "mentions", label: "Someone mentioned you", in_app: true, email: false, email_available: true },
    { category: "blockers", label: "A teammate reported a blocker", in_app: true, email: false, email_available: false },
  ],
}; // prettier-ignore

function wrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function show() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <NotificationPreferencesCard />
      <Toaster />
    </QueryClientProvider>,
  );
}

const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });

describe("NotificationPreferencesCard", () => {
  it("lists every row, with an email switch only where there is an email", async () => {
    server.use(http.get("*/api/v1/notification-preferences", () => HttpResponse.json(PREFS)));
    show();
    expect(await screen.findByText("Someone mentioned you")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Someone mentioned you: in DevSync" })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Someone mentioned you: by email" })).not.toBeChecked();
    expect(
      screen.queryByRole("switch", { name: "A teammate reported a blocker: by email" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("No email for this one")).toBeInTheDocument();
    expect(screen.getByText(/Account and security emails/)).toBeInTheDocument();
  });

  it("saves one row as soon as a switch changes", async () => {
    let sent: unknown = null;
    server.use(
      csrf(),
      http.get("*/api/v1/notification-preferences", () => HttpResponse.json(PREFS)),
      http.put("*/api/v1/notification-preferences", async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({
          items: [{ ...PREFS.items[0], email: true }, PREFS.items[1]],
        });
      }),
    );
    show();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("switch", { name: "Someone mentioned you: by email" }));
    expect(sent).toEqual({ items: [{ category: "mentions", in_app: true, email: true }] });
    expect(screen.getByRole("switch", { name: "Someone mentioned you: by email" })).toBeChecked();
  });

  it("moves a switch back and says why when the save is refused", async () => {
    server.use(
      csrf(),
      http.get("*/api/v1/notification-preferences", () => HttpResponse.json(PREFS)),
      http.put("*/api/v1/notification-preferences", () =>
        HttpResponse.json(
          { error: { code: "VALIDATION_ERROR", message: "This kind of notification has no email." } },
          { status: 422 },
        ),
      ),
    );
    show();
    const user = userEvent.setup();
    const toggle = await screen.findByRole("switch", { name: "Someone mentioned you: in DevSync" });
    await user.click(toggle);
    expect(await screen.findByText(/has no email|Some fields need attention/)).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Someone mentioned you: in DevSync" })).toBeChecked();
  });

  it("explains a failed load", async () => {
    server.use(
      http.get("*/api/v1/notification-preferences", () =>
        HttpResponse.json({ error: { code: "INTERNAL_ERROR", message: "x" } }, { status: 500 }),
      ),
    );
    show();
    const card = await screen.findByText("Your notification settings didn’t load");
    expect(within(card.closest("div") ?? document.body).getByText(/didn’t load/)).toBeInTheDocument();
  });
});

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  readyState = FakeEventSource.CONNECTING;
  closed = false;
  listeners = new Map<string, ((e: MessageEvent<string>) => void)[]>();
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(name: string, fn: (e: MessageEvent<string>) => void) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), fn]);
  }
  emit(name: string, data = "") {
    for (const fn of this.listeners.get(name) ?? []) fn(new MessageEvent(name, { data }));
  }
  close() {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }
}

describe("useNotificationStream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("stays closed while signed out", () => {
    const qc = new QueryClient();
    renderHook(() => { useNotificationStream(false); }, { wrapper: wrapper(qc) });
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("re-reads notifications on each event and retries after the browser gives up", () => {
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    const { unmount } = renderHook(() => { useNotificationStream(true); }, { wrapper: wrapper(qc) });
    const first = FakeEventSource.instances[0];
    if (!first) throw new Error("no stream opened");
    expect(first.url).toBe("/api/v1/notifications/stream");
    act(() => {
      first.emit("notification", JSON.stringify({ id: "n1", type: "MENTIONED", title: "Hi" }));
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["notifications"] });
    act(() => {
      first.readyState = FakeEventSource.CONNECTING;
      first.emit("error"); // the browser is reconnecting by itself: nothing to do
    });
    expect(FakeEventSource.instances).toHaveLength(1);
    act(() => {
      first.readyState = FakeEventSource.CLOSED;
      first.emit("error"); // it gave up
    });
    expect(FakeEventSource.instances).toHaveLength(1);
    act(() => {
      vi.advanceTimersByTime(STREAM_BACKOFF[0]);
    });
    expect(FakeEventSource.instances).toHaveLength(2);
    unmount();
    expect(FakeEventSource.instances[1]?.closed).toBe(true);
  });
});
