import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { ApiError } from "@/api/client";
import { clearToasts, dismissToast, toast, useToasts } from "@/components/ui/toast-store";
import { renderHook } from "@testing-library/react";
import { server } from "@/test/server";
import { NAV, UPCOMING } from "./navigation";
import { createQueryClient, feedbackFor } from "./queryClient";
import { titleFor } from "./Root";

function latest() {
  const { result } = renderHook(() => useToasts());
  return result.current;
}

describe("global error feedback (spec §13.7)", () => {
  afterEach(() => {
    clearToasts();
  });

  it("toasts 403 and 429 with the wait time; ignores other errors", () => {
    feedbackFor(new ApiError(403, { error: { message: "Only the client can do this." } }, null));
    feedbackFor(new ApiError(429, null, 90));
    feedbackFor(new ApiError(500, null, null));
    feedbackFor(new Error("plain"));
    const items = latest();
    expect(items.map((t) => t.title)).toEqual([
      "You can’t do that with this account.",
      "Too many requests",
    ]);
    expect(items[1]?.description).toBe("Try again in 2 minutes.");
    feedbackFor(new ApiError(429, null, 30));
    expect(latest().at(-1)?.description).toBe("Try again in 30 seconds.");
  });

  it("does not toast for mutations that show their own errors", async () => {
    server.use(
      http.get("*/api/v1/auth/csrf", () => {
        document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
        return new HttpResponse(null, { status: 204 });
      }),
      http.post("*/api/v1/x", () =>
        HttpResponse.json({ error: { code: "RATE_LIMITED" } }, { status: 429 }),
      ),
    );
    const client = createQueryClient();
    const { api } = await import("@/api/client");
    const quiet = client.getMutationCache().build(client, {
      mutationFn: () => api("/x", { method: "POST" }),
      meta: { inlineErrors: true },
    });
    await quiet.execute(undefined).catch(() => undefined);
    expect(latest()).toEqual([]);
    const loud = client
      .getMutationCache()
      .build(client, { mutationFn: () => api("/x", { method: "POST" }) });
    await loud.execute(undefined).catch(() => undefined);
    expect(latest()).toHaveLength(1);
  });
});

describe("toast store", () => {
  afterEach(() => {
    clearToasts();
  });

  it("does not stack identical messages and keeps at most four", () => {
    toast({ title: "Saved" });
    toast({ title: "Saved" });
    expect(latest()).toHaveLength(1);
    for (let i = 0; i < 6; i += 1) toast({ title: `t${String(i)}` });
    expect(latest()).toHaveLength(4);
    const id = latest()[0]?.id ?? 0;
    dismissToast(id);
    expect(latest().some((t) => t.id === id)).toBe(false);
  });
});

describe("navigation (spec §13.4)", () => {
  it("lists the sidebars from the spec and four-slot tab bars", () => {
    expect(NAV.DEVELOPER.sidebar.map((i) => i.label)).toEqual([
      "Dashboard",
      "Find projects",
      "My bids",
      "My projects",
      "Skill challenges",
      "Profile & portfolio",
      "Reputation",
      "Earnings",
      "Notifications",
      "Settings",
    ]);
    expect(NAV.CLIENT.sidebar.map((i) => i.label)).toEqual([
      "Dashboard",
      "Create project",
      "My projects",
      "Teams",
      "Payments",
      "Disputes",
      "Analytics",
      "Notifications",
      "Settings",
    ]);
    expect(NAV.DEVELOPER.tabs.map((t) => t.label)).toEqual(["Home", "Find work", "My projects"]);
    expect(NAV.CLIENT.tabs.map((t) => t.label)).toEqual(["Home", "Projects", "Payments"]);
  });

  it("gives every not-yet-built page a phase, once", () => {
    const paths = UPCOMING.map((i) => i.to);
    expect(new Set(paths).size).toBe(paths.length);
    expect(UPCOMING.every((i) => (i.phase ?? 0) >= 4)).toBe(true);
    expect(paths).not.toContain("/settings");
  });

  it("titles pages as '<Page> · DevSync'", () => {
    expect(titleFor("Settings")).toBe("Settings · DevSync");
    expect(titleFor(undefined)).toBe("DevSync · Plan, hire a fair team, deliver");
  });
});
