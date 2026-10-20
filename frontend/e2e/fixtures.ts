/** Helpers for Phase 1 E2E tests: talk to the test-only API routes (DEVSYNC_ENV=test). */
import type { APIRequestContext, Page } from "@playwright/test";

export const PASSWORD = "correct horse battery staple 42!";

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${String(Date.now())}-${String(Math.floor(Math.random() * 1e6))}@example.com`;
}

export function uniquePhone(): string {
  return `+88017${String(Math.floor(10_000_000 + Math.random() * 89_999_999))}`;
}

export async function csrfHeaders(
  request: APIRequestContext,
  baseURL: string,
): Promise<Record<string, string>> {
  await request.get("/api/v1/auth/csrf");
  const state = await request.storageState();
  const token = state.cookies.find((c) => c.name === "__Host-ds_csrf")?.value ?? "";
  return { "X-CSRF-Token": token, Origin: new URL(baseURL).origin };
}

export interface Seeded {
  userId: string;
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
  const body = (await response.json()) as { user_id: string; totp_secret: string | null };
  return { userId: body.user_id, email, password: PASSWORD, totpSecret: body.totp_secret };
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

/** The §18.2 "Online ordering system" plan: name, days, share (basis points), predecessors. */
export const ORDERING_PLAN: [string, number, number, string[]][] = [
  ["Requirements & design", 4, 1000, []],
  ["Database", 5, 1500, ["Requirements & design"]],
  ["Backend API", 8, 2500, ["Database"]],
  ["Frontend", 9, 2000, ["Requirements & design"]],
  ["Integration", 3, 1000, ["Backend API", "Frontend"]],
  ["Testing & launch", 4, 2000, ["Integration"]],
];

/** Build the §18.2 project for the signed-in client through the API (a deterministic draft with
 * a fixed start date, optionally published). Returns the project id. */
export async function createOrderingProject(
  page: Page,
  baseURL: string,
  { publish = false }: { publish?: boolean } = {},
): Promise<string> {
  const req = page.request;
  const ok = async (r: Awaited<ReturnType<APIRequestContext["get"]>>) => {
    if (!r.ok()) throw new Error(`${r.url()} → ${String(r.status())} ${await r.text()}`);
    return (await r.json()) as Record<string, unknown>;
  };
  const skills = (await (await req.get("/api/v1/skills")).json()) as { id: string; name: string }[];
  const skill = (name: string) => skills.find((s) => s.name === name)?.id ?? "";
  const project = await ok(
    await req.post("/api/v1/projects", {
      headers: await csrfHeaders(req, baseURL),
      data: {
        title: "Online ordering system",
        summary: "Customers order online; staff track orders.",
        description: "",
        requirements: "Ordering, simulated payments and order tracking.",
        budget_paisa: 12_000_000,
        bonus_pool_paisa: 0,
        deadline_days: 30,
        team_size: 4,
        start_date: "2026-11-02",
      },
    }),
  );
  const id = String(project.id);
  await ok(
    await req.put(`/api/v1/projects/${id}/slots`, {
      headers: await csrfHeaders(req, baseURL),
      data: {
        slots: ["React", "FastAPI", "PostgreSQL", "Testing"].map((n) => ({
          skill_id: skill(n),
          count: 1,
        })),
      },
    }),
  );
  const saved = (await (
    await req.put(`/api/v1/projects/${id}/milestones`, {
      headers: await csrfHeaders(req, baseURL),
      data: {
        milestones: ORDERING_PLAN.map(([name, days, share]) => ({
          name,
          description: "",
          duration_days: days,
          share_bp: share,
          skill_ids: [],
        })),
      },
    })
  ).json()) as { id: string; name: string }[];
  const idOf = (name: string) => saved.find((m) => m.name === name)?.id ?? "";
  await ok(
    await req.put(`/api/v1/projects/${id}/dependencies`, {
      headers: await csrfHeaders(req, baseURL),
      data: {
        dependencies: ORDERING_PLAN.flatMap(([name, , , preds]) =>
          preds.map((p) => ({ predecessor_id: idOf(p), successor_id: idOf(name) })),
        ),
      },
    }),
  );
  if (publish) {
    const verified = await req.post("/api/v1/me/payment-method/verify", {
      headers: await csrfHeaders(req, baseURL),
    });
    if (verified.status() !== 204) throw new Error(`verify → ${String(verified.status())}`);
    await ok(
      await req.post(`/api/v1/projects/${id}/publish`, {
        headers: await csrfHeaders(req, baseURL),
        data: {},
      }),
    );
  }
  return id;
}
