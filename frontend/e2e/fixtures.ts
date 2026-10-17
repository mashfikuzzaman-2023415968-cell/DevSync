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
