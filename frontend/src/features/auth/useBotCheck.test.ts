import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { botTiming, useBotCheck } from "./useBotCheck";

describe("useBotCheck", () => {
  afterEach(() => {
    vi.useRealTimers();
    botTiming.minFillMs = 0;
  });

  it("waits until the minimum fill time has passed before answering", async () => {
    vi.useFakeTimers();
    botTiming.minFillMs = 2000;
    const { result } = renderHook(() => useBotCheck());
    let done = false;
    let fields: Awaited<ReturnType<typeof result.current.fields>> | undefined;
    act(() => {
      void result.current.fields(false).then((f) => {
        fields = f;
        done = true;
      });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(done).toBe(false);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(700);
    });
    expect(done).toBe(true);
    expect(fields).toMatchObject({ captcha: null, website: "" });
    expect(Date.now() - (fields?.started_at_ms ?? 0)).toBeGreaterThanOrEqual(2000);
  });

  it("answers at once when the form has been open long enough", async () => {
    botTiming.minFillMs = 1;
    const { result } = renderHook(() => useBotCheck());
    await new Promise((r) => setTimeout(r, 150));
    const fields = await act(() => result.current.fields(false));
    expect(fields.captcha).toBeNull();
  });
});
