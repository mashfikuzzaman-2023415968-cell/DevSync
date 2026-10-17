import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { cn } from "./cn";
import {
  formatCount,
  formatDate,
  formatDays,
  formatMoney,
  formatPercent,
  formatRelative,
  formatScore,
} from "./format";
import { installNonce, readNonce } from "./nonce";
import { reportClientError, resetReportBudget, summarize } from "./reportError";
import { readPref, writePref } from "./storage";

describe("format (spec §13.1, §13.8 #4)", () => {
  it("formats paisa as taka with Bangladeshi grouping", () => {
    expect(formatMoney(1_250_000)).toBe("৳12,500");
    expect(formatMoney(12_000_000_00)).toBe("৳1,20,00,000");
    expect(formatMoney(12_345)).toBe("৳123.45");
    expect(formatMoney(-50_000)).toBe("−৳500");
    expect(formatMoney(0)).toBe("৳0");
  });

  it("abbreviates large counts and keeps small ones exact", () => {
    expect(formatCount(999)).toBe("999");
    expect(formatCount(12_400)).toBe("12.4k");
    expect(formatCount(1000)).toBe("1k");
    expect(formatCount(2_500_000)).toBe("2.5M");
    expect(formatCount(150_000)).toBe("150k");
  });

  it("shows percentages with at most one decimal and scores as 0–100", () => {
    expect(formatPercent(0.873)).toBe("87.3%");
    expect(formatPercent(0.5)).toBe("50%");
    expect(formatScore(0.666)).toBe("67");
    expect(formatScore(1.4)).toBe("100");
    expect(formatScore(-0.2)).toBe("0");
  });

  it("formats dates in Dhaka time and days with plurals", () => {
    expect(formatDate("2026-11-01T20:00:00Z")).toBe("2 Nov 2026");
    expect(formatDays(1)).toBe("1 day");
    expect(formatDays(4)).toBe("4 days");
  });

  it("describes relative times", () => {
    const now = new Date("2026-10-17T12:00:00Z");
    expect(formatRelative("2026-10-15T12:00:00Z", now)).toBe("2 days ago");
    expect(formatRelative("2026-10-17T15:00:00Z", now)).toBe("in 3 hours");
    expect(formatRelative("2026-10-17T11:59:40Z", now)).toBe("just now");
  });
});

describe("cn", () => {
  it("keeps DevSync size and colour utilities apart and resolves real conflicts", () => {
    expect(cn("text-body text-text")).toBe("text-body text-text");
    expect(cn("text-body", "text-h3")).toBe("text-h3");
    expect(cn("px-2", undefined, null, "px-4")).toBe("px-4");
    expect(cn("shadow-xs", "shadow-md")).toBe("shadow-md");
  });
});

describe("storage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("reads, writes and removes preferences", () => {
    writePref("k", "v");
    expect(readPref("k")).toBe("v");
    writePref("k", null);
    expect(readPref("k")).toBeNull();
  });

  it("never throws when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readPref("k")).toBeNull();
    expect(() => {
      writePref("k", "v");
    }).not.toThrow();
  });
});

describe("CSP style nonce (D23)", () => {
  function doc(content: string): Document {
    const d = document.implementation.createHTMLDocument("t");
    const meta = d.createElement("meta");
    meta.name = "csp-nonce";
    meta.content = content;
    d.head.append(meta);
    return d;
  }

  it("accepts only a 32-hex nonce from Nginx", () => {
    expect(readNonce(doc("0123456789abcdef0123456789abcdef"))).toBe(
      "0123456789abcdef0123456789abcdef",
    );
    expect(readNonce(doc("__CSP_NONCE__"))).toBeUndefined();
    expect(readNonce(doc("abc' 'unsafe-inline"))).toBeUndefined();
    expect(installNonce(doc("__CSP_NONCE__"))).toBeUndefined();
  });
});

describe("client error reports", () => {
  afterEach(() => {
    resetReportBudget();
  });

  it("sends only the path and truncated text", () => {
    window.history.pushState({}, "", "/reset-password?token=secret#frag");
    const s = summarize(new Error("x".repeat(900)), "render");
    expect(s.path).toBe("/reset-password");
    expect(s.message.length).toBe(500);
    expect(s.kind).toBe("render");
    window.history.pushState({}, "", "/");
  });

  it("sends at most five reports per page view and never throws", async () => {
    let posts = 0;
    server.use(
      http.get("*/api/v1/auth/csrf", () => {
        document.cookie = "__Host-ds_csrf=t.s; path=/; secure";
        return new HttpResponse(null, { status: 204 });
      }),
      http.post("*/api/v1/client-errors", () => {
        posts += 1;
        return HttpResponse.json({ error: { code: "RATE_LIMITED" } }, { status: 429 });
      }),
    );
    for (let i = 0; i < 8; i += 1) await reportClientError(new Error(`e${String(i)}`));
    expect(posts).toBe(5);
  });
});
