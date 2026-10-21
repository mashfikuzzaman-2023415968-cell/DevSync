import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { ApiError, api } from "./client";

describe("api client", () => {
  it("adds the CSRF header from the cookie on unsafe requests, fetching it first if missing", async () => {
    document.cookie = "__Host-ds_csrf=; path=/; secure; max-age=0";
    let seen: string | null = null;
    server.use(
      http.get("*/api/v1/auth/csrf", () => {
        document.cookie = "__Host-ds_csrf=nonce.sig; path=/; secure";
        return new HttpResponse(null, { status: 204 });
      }),
      http.post("*/api/v1/things", ({ request }) => {
        seen = request.headers.get("X-CSRF-Token");
        return HttpResponse.json({ ok: true });
      }),
    );
    await expect(api("/things", { method: "POST", body: {} })).resolves.toEqual({ ok: true });
    expect(seen).toBe("nonce.sig");
  });

  it("uses the echoed token when the new cookie isn't readable yet, with one shared fetch", async () => {
    document.cookie = "__Host-ds_csrf=; path=/; secure; max-age=0";
    let fetches = 0;
    const seen: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/auth/csrf", () => {
        fetches += 1;
        // The cookie reaches document.cookie late (WebKit); only the header carries it now.
        return new HttpResponse(null, { status: 204, headers: { "X-CSRF-Token": "late.sig" } });
      }),
      http.post("*/api/v1/things", ({ request }) => {
        seen.push(request.headers.get("X-CSRF-Token"));
        return HttpResponse.json({ ok: true });
      }),
    );
    await Promise.all([
      api("/things", { method: "POST", body: {} }),
      api("/things", { method: "POST", body: {} }),
    ]);
    expect(fetches).toBe(1);
    expect(seen).toEqual(["late.sig", "late.sig"]);
  });

  it("does not send CSRF on GET and returns undefined for 204", async () => {
    let header: string | null = "unset";
    server.use(
      http.get("*/api/v1/empty", ({ request }) => {
        header = request.headers.get("X-CSRF-Token");
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await expect(api("/empty")).resolves.toBeUndefined();
    expect(header).toBeNull();
  });

  it("parses the error envelope, fields and Retry-After", async () => {
    server.use(
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json(
          {
            error: {
              code: "RATE_LIMITED",
              message: "Too many attempts.",
              fields: { email: "bad" },
              request_id: "req_1",
              retry_after: 12,
            },
          },
          { status: 429, headers: { "Retry-After": "12" } },
        ),
      ),
    );
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    const error = (await api("/auth/login", { method: "POST", body: {} }).catch(
      (e: unknown) => e,
    )) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(429);
    expect(error.code).toBe("RATE_LIMITED");
    expect(error.retryAfter).toBe(12);
    expect(error.fields).toEqual({ email: "bad" });
    expect(error.requestId).toBe("req_1");
  });

  it("retries GETs on network errors but not POSTs", async () => {
    let gets = 0;
    let posts = 0;
    server.use(
      http.get("*/api/v1/flaky", () => {
        gets += 1;
        return gets < 2 ? HttpResponse.error() : HttpResponse.json({ ok: 1 });
      }),
      http.post("*/api/v1/flaky", () => {
        posts += 1;
        return HttpResponse.error();
      }),
    );
    document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
    await expect(api("/flaky")).resolves.toEqual({ ok: 1 });
    expect(gets).toBe(2);
    await expect(api("/flaky", { method: "POST" })).rejects.toMatchObject({
      status: 0,
      code: "NETWORK_ERROR",
    });
    expect(posts).toBe(1);
  });

  it("gives friendly defaults when the server sends no envelope", () => {
    expect(new ApiError(500, null, null).message).toMatch(/our side/);
    expect(new ApiError(0, null, null).message).toMatch(/offline/);
    expect(new ApiError(429, null, null).message).toMatch(/Too many/);
    expect(new ApiError(400, null, null).code).toBe("UNKNOWN");
  });
});
