// The transport seam — THE ONLY FILE IN THE APP THAT KNOWS `fetch` EXISTS.
//
// CLAUDE.md RULE 1: everything above this file depends on the `HttpClient` interface, never on
// the mechanism behind it. Swapping to Axios (for interceptors, when auth lands) means writing
// a second `createAxiosClient` here and changing the one `httpClient` export below — no route,
// no component, and no type outside this file changes. That is the reason for the layering.

import { ApiError } from "./types";

export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export type QueryValue = string | number | boolean | null | undefined;

export interface RequestConfig {
  /** Caller's abort signal — `usePolling` passes one so unmounts cancel in-flight requests. */
  signal?: AbortSignal;
  /** Query string params. `null`/`undefined` values are omitted; everything is URI-encoded. */
  query?: Record<string, QueryValue>;
  /** Per-call override of the client's default timeout. */
  timeoutMs?: number;
}

/** What the layers above depend on. Any transport implementing this is a drop-in swap. */
export interface HttpClient {
  send<T>(
    method: Method,
    path: string,
    body?: unknown,
    config?: RequestConfig,
  ): Promise<T>;
}

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:9001"
).replace(/\/$/, "");

const DEFAULT_TIMEOUT_MS = 15_000;

function buildUrl(baseUrl: string, path: string, query?: Record<string, QueryValue>): string {
  if (!query) return `${baseUrl}${path}`;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) params.append(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${baseUrl}${path}?${qs}` : `${baseUrl}${path}`;
}

/** Abort on EITHER the caller's signal or the timeout, and always clean up the listener. */
function linkSignals(signal: AbortSignal | undefined, timeoutMs: number) {
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(new DOMException(`timed out after ${timeoutMs}ms`, "TimeoutError")),
    timeoutMs,
  );
  const forward = () => controller.abort(signal?.reason);
  if (signal) {
    if (signal.aborted) forward();
    else signal.addEventListener("abort", forward, { once: true });
  }
  return {
    signal: controller.signal,
    release: () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", forward);
    },
  };
}

async function toApiError(res: Response): Promise<ApiError> {
  let detail = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") detail = body.detail;
  } catch {
    // Non-JSON error body — the status line above is the best we have.
  }
  return new ApiError(res.status, detail);
}

export function createFetchClient(
  baseUrl: string,
  defaultTimeoutMs = DEFAULT_TIMEOUT_MS,
): HttpClient {
  return {
    async send<T>(
      method: Method,
      path: string,
      body?: unknown,
      config?: RequestConfig,
    ): Promise<T> {
      const { signal, query, timeoutMs = defaultTimeoutMs } = config ?? {};
      const init: RequestInit = { method, cache: "no-store" };

      if (body !== undefined) {
        if (body instanceof FormData) {
          // Never set Content-Type here — the browser must add its own multipart boundary.
          init.body = body;
        } else {
          init.headers = { "Content-Type": "application/json" };
          init.body = JSON.stringify(body);
        }
      }

      const link = linkSignals(signal, timeoutMs);
      init.signal = link.signal;
      try {
        const res = await fetch(buildUrl(baseUrl, path, query), init);
        if (!res.ok) throw await toApiError(res);
        if (res.status === 204) return undefined as T;
        return (await res.json()) as T;
      } finally {
        link.release();
      }
    },
  };
}

/** The app's live client. Replace this one line to change transport. */
export const httpClient: HttpClient = createFetchClient(API_BASE);
