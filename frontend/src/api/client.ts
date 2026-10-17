/**
 * Fetch wrapper for the DevSync API (spec §13.7):
 * - same-origin credentials (session cookie), JSON only;
 * - CSRF: unsafe requests carry `X-CSRF-Token` from the `__Host-ds_csrf` cookie,
 *   fetched from `/auth/csrf` first if missing;
 * - 15-second timeout; GET requests retry twice on network errors with backoff;
 * - errors become `ApiError` with the server's code, message, field errors and
 *   `Retry-After` (callers decide how to show them; 401 redirects are handled by
 *   the route guards so auth screens can show their own messages; 403/429 toasts come
 *   from the query client in app/queryClient.ts);
 * - network failures raise a `ds:network` event so the offline banner can appear.
 */
import { readCookie } from "@/lib/cookies";

export const API_BASE = "/api/v1";
const CSRF_COOKIE = "__Host-ds_csrf";
const TIMEOUT_MS = 15_000;
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);
/** Fired on window after every request: detail.online is false when the network failed. */
export const NETWORK_EVENT = "ds:network";

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
    window.dispatchEvent(new CustomEvent(NETWORK_EVENT, { detail: { online: false } }));
    throw new ApiError(0, null, null);
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abortFromCaller);
  }

  window.dispatchEvent(new CustomEvent(NETWORK_EVENT, { detail: { online: true } }));
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const parsed: unknown = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const retry = Number(response.headers.get("Retry-After"));
    throw new ApiError(response.status, parsed as ErrorBody | null, retry > 0 ? retry : null);
  }
  return parsed as T;
}

/** Multipart upload with progress (0–1). XMLHttpRequest because fetch can't report upload
 * progress; same CSRF, credentials and error envelope as `api`. */
export async function upload<T>(
  path: string,
  form: FormData,
  onProgress?: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<T> {
  const token = await ensureCsrf();
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${path}`);
    xhr.withCredentials = true;
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("X-CSRF-Token", token);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onerror = () => {
      window.dispatchEvent(new CustomEvent(NETWORK_EVENT, { detail: { online: false } }));
      reject(new ApiError(0, null, null));
    };
    xhr.onabort = () => {
      reject(new ApiError(0, null, null));
    };
    xhr.onload = () => {
      let parsed: unknown = null;
      try {
        parsed = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        parsed = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(parsed as T);
        return;
      }
      const retry = Number(xhr.getResponseHeader("Retry-After"));
      reject(new ApiError(xhr.status, parsed as ErrorBody | null, retry > 0 ? retry : null));
    };
    signal?.addEventListener("abort", () => {
      xhr.abort();
    });
    xhr.send(form);
  });
}

/** Where an image or document is fetched from (the API redirects to a short-lived link). */
export function fileUrl(fileId: string): string {
  return `${API_BASE}/files/${fileId}/download`;
}
