/**
 * Fetch wrapper for the DevSync API (spec §13.7):
 * - same-origin credentials (session cookie), JSON only;
 * - CSRF: unsafe requests carry `X-CSRF-Token` from the `__Host-ds_csrf` cookie,
 *   fetched from `/auth/csrf` first if missing;
 * - 15-second timeout; GET requests retry twice on network errors with backoff;
 * - errors become `ApiError` with the server's code, message, field errors and
 *   `Retry-After` (callers decide how to show them; 401 redirects are handled by
 *   the route guards so auth screens can show their own messages).
 */
import { readCookie } from "@/lib/cookies";

export const API_BASE = "/api/v1";
const CSRF_COOKIE = "__Host-ds_csrf";
const TIMEOUT_MS = 15_000;
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export interface ErrorBody {
  error?: {
    code?: string;
    message?: string;
    fields?: Record<string, string>;
    request_id?: string | null;
    [key: string]: unknown;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: Record<string, string>;
  readonly requestId: string | null;
  readonly retryAfter: number | null;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ErrorBody | null, retryAfter: number | null) {
    const err = body?.error ?? {};
    super(err.message ?? defaultMessage(status));
    this.name = "ApiError";
    this.status = status;
    this.code = err.code ?? (status === 0 ? "NETWORK_ERROR" : "UNKNOWN");
    this.fields = err.fields ?? {};
    this.requestId = err.request_id ?? null;
    this.retryAfter = retryAfter;
    this.details = err;
  }
}

function defaultMessage(status: number): string {
  if (status === 0) return "You appear to be offline. Check your connection and try again.";
  if (status === 429) return "Too many requests. Please wait and try again.";
  if (status >= 500) return "Something went wrong on our side. Please try again.";
  return "The request could not be completed.";
}

async function ensureCsrf(): Promise<string> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) return existing;
  await fetch(`${API_BASE}/auth/csrf`, { credentials: "same-origin" });
  return readCookie(CSRF_COOKIE) ?? "";
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const attempts = method === "GET" ? 3 : 1;
  let lastError: ApiError | null = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await send<T>(path, method, options);
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 0) throw error;
      lastError = error;
      await sleep(400 * 2 ** attempt);
    }
  }
  throw lastError ?? new ApiError(0, null, null);
}

async function send<T>(path: string, method: string, options: RequestOptions): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method)) headers["X-CSRF-Token"] = await ensureCsrf();

  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort();
  }, TIMEOUT_MS);
  const abortFromCaller = () => {
    controller.abort();
  };
  options.signal?.addEventListener("abort", abortFromCaller);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      credentials: "same-origin",
      body: options.body === undefined ? null : JSON.stringify(options.body),
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(0, null, null);
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abortFromCaller);
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const parsed: unknown = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const retry = Number(response.headers.get("Retry-After"));
    throw new ApiError(response.status, parsed as ErrorBody | null, retry > 0 ? retry : null);
  }
  return parsed as T;
}
