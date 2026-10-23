/** Cache hygiene: what a sign-in and a bid do to cached data (audit fixes). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { useCreateBid } from "@/features/bids/api";
import { meKey, startSession } from "@/features/auth/api";
import { server } from "@/test/server";

const csrf = () =>
  http.get("*/api/v1/auth/csrf", () => {
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    return new HttpResponse(null, { status: 204 });
  });

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
}

describe("a new sign-in", () => {
  it("drops the previous user's cached data and reads the new user", async () => {
    server.use(http.get("*/api/v1/me", () => HttpResponse.json({ id: "u-new", role: "CLIENT" })));
    const qc = client();
    qc.setQueryData(meKey, { id: "u-old", role: "DEVELOPER" });
    qc.setQueryData(["projects", "recommended"], [{ project: { id: "p-old" } }]);
    qc.setQueryData(["me", "bids"], [{ id: "b-old" }]);
    qc.setQueryData(["sessions"], { items: [{ id: "s-old" }] });
    // An observer, as the guard would have, so `me` can be refetched.
    qc.getQueryCache()
      .find({ queryKey: meKey })
      ?.setOptions({
        queryKey: meKey,
        queryFn: () => fetch("/api/v1/me").then((r) => r.json() as Promise<unknown>),
      });

    await startSession(qc);

    expect(qc.getQueryData(["projects", "recommended"])).toBeUndefined();
    expect(qc.getQueryData(["me", "bids"])).toBeUndefined();
    expect(qc.getQueryData(["sessions"])).toBeUndefined();
    expect(qc.getQueryData(meKey)).toEqual({ id: "u-new", role: "CLIENT" });
  });
});

describe("placing a bid", () => {
  it("marks the recommendations stale so Find work refetches them", async () => {
    server.use(
      csrf(),
      http.post("*/api/v1/projects/p1/bids", () => HttpResponse.json({ id: "b1" })),
    );
    const qc = client();
    qc.setQueryData(["projects", "recommended"], [{ project: { id: "p1" } }]);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useCreateBid("p1"), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({
        slot_id: "s1",
        price_paisa: 100_000,
        days_needed: 10,
        hours_per_week_committed: 20,
      } as never);
    });
    expect(qc.getQueryState(["projects", "recommended"])?.isInvalidated).toBe(true);
  });
});
