import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { botTiming } from "@/features/auth/useBotCheck";
import { server } from "./server";

// The 2 s minimum fill time is covered by useBotCheck.test.ts; other tests skip it.
botTiming.minFillMs = 0;

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
});
afterEach(() => {
  cleanup();
  server.resetHandlers();
  document.cookie.split(";").forEach((c) => {
    const name = c.split("=")[0]?.trim();
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; secure`;
  });
});
afterAll(() => {
  server.close();
});
