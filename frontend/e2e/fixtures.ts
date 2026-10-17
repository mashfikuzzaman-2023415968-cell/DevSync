/** Helpers for Phase 1 E2E tests: talk to the test-only API routes (DEVSYNC_ENV=test). */
import type { APIRequestContext, Page } from "@playwright/test";

export const PASSWORD = "correct horse battery staple 42!";

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${String(Date.now())}-${String(Math.floor(Math.random() * 1e6))}@example.com`;
}

export function uniquePhone(): string {
  return `+88017${String(Math.floor(10_000_000 + Math.random() * 89_999_999))}`;
}

async function csrfHeaders(
  request: APIRequestContext,
  baseURL: string,
): Promise<Record<string, string>> {
  await request.get("/api/v1/auth/csrf");
  const state = await request.storageState();
  const token = state.cookies.find((c) => c.name === "__Host-ds_csrf")?.value ?? "";
  return { "X-CSRF-Token": token, Origin: new URL(baseURL).origin };
}

export interface Seeded {
  email: string;
  password: string;
  totpSecret: string | null;
}

export async function seedUser(
  request: APIRequestContext,
  baseURL: string,
  role: "CLIENT" | "DEVELOPER" | "ADMIN",
  displayName = "Test User",
): Promise<Seeded> {
  const email = uniqueEmail(role.toLowerCase());
  const response = await request.post("/api/v1/__test__/seed/user", {
    headers: await csrfHeaders(request, baseURL),
    data: {
      role,
      email,
      phone: role === "ADMIN" ? null : uniquePhone(),
      password: PASSWORD,
      verified: true,
      with_totp: true,
      display_name: displayName,
    },
  });
  if (!response.ok())
    throw new Error(`seed failed: ${String(response.status())} ${await response.text()}`);
  const body = (await response.json()) as { totp_secret: string | null };
  return { email, password: PASSWORD, totpSecret: body.totp_secret };
}

export async function lastSms(request: APIRequestContext, phone: string): Promise<string> {
  const r = await request.get(`/api/v1/__test__/sms?phone=${encodeURIComponent(phone)}`);
  const body = (await r.json()) as { message: string | null };
  return body.message?.split(" ").pop() ?? "";
}

export async function lastLink(
  request: APIRequestContext,
  to: string,
  template: string,
): Promise<string> {
  const r = await request.get(
    `/api/v1/__test__/email-link?to=${encodeURIComponent(to)}&template=${template}`,
  );
  const body = (await r.json()) as { link: string | null };
  return body.link ?? "";
}

export async function totpNow(request: APIRequestContext, secret: string): Promise<string> {
  const r = await request.get(`/api/v1/__test__/totp?secret=${secret}`);
  return ((await r.json()) as { code: string }).code;
}

export async function signIn(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: /Sign in|Checking/ }).click();
}

/** Seed a user and sign the page's browser context in through the API (no UI, no fill-time
 * wait); admins also pass TOTP. The context's cookie jar is shared with the page. */
export async function apiSignIn(
  page: Page,
  baseURL: string,
  role: "CLIENT" | "DEVELOPER" | "ADMIN",
  displayName = "Nadia Rahman",
): Promise<Seeded> {
  const user = await seedUser(page.request, baseURL, role, displayName);
  const headers = await csrfHeaders(page.request, baseURL);
  let r = await page.request.post("/api/v1/auth/login", {
    headers,
    data: { email: user.email, password: user.password, captcha: "test-bypass" },
  });
  if (!r.ok()) throw new Error(`login failed: ${String(r.status())} ${await r.text()}`);
  const body = (await r.json()) as { status: string; pre_auth?: string };
  if (body.status === "TOTP_REQUIRED") {
    const code = await totpNow(page.request, user.totpSecret ?? "");
    r = await page.request.post("/api/v1/auth/login/totp", {
      headers: await csrfHeaders(page.request, baseURL),
      data: { pre_auth: body.pre_auth, code },
    });
    if (!r.ok()) throw new Error(`totp failed: ${String(r.status())}`);
  }
  return user;
}

/** Listen for CSP violations and console errors from the first script on (spec §14.3). */
export async function watchPage(page: Page, origin: string) {
  const consoleErrors: string[] = [];
  const foreign: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    // Signed-out visitors get the expected 401 from the session check.
    if (msg.location().url.endsWith("/api/v1/me") && msg.text().includes("401")) return;
    consoleErrors.push(msg.text());
  });
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (url.protocol.startsWith("http") && url.origin !== origin) foreign.push(req.url());
  });
  await page.addInitScript(() => {
    (window as unknown as { __csp: string[] }).__csp = [];
    document.addEventListener("securitypolicyviolation", (e) => {
      (window as unknown as { __csp: string[] }).__csp.push(
        `${e.violatedDirective} ${e.blockedURI}`,
      );
    });
  });
  return {
    consoleErrors,
    foreign,
    violations: () => page.evaluate(() => (window as unknown as { __csp: string[] }).__csp),
  };
}
