/**
 * Shared Playwright `test`: before every test, clear the API's rate-limit counters through the
 * test-only router (DEVSYNC_ENV=test). All E2E traffic comes from one container IP, so without
 * this, independent tests would throttle each other under the real per-IP limits (§14.8).
 */
import { test as base, type APIRequestContext } from "@playwright/test";

export async function resetLimits(request: APIRequestContext): Promise<void> {
  const r = await request.get("/api/v1/__test__/ratelimits/reset");
  if (r.status() !== 204) throw new Error(`rate-limit reset failed: ${String(r.status())}`);
}

export const test = base.extend<{ freshLimits: undefined }>({
  freshLimits: [
    async ({ request }, use) => {
      await resetLimits(request);
      await use(undefined);
    },
    { auto: true },
  ],
});

export { expect } from "@playwright/test";
