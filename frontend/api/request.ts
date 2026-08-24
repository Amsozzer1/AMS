// The single verb every route is written against.
//
// It exists so `routes.ts` imports `request` and NEVER imports the client. That one hop is
// what makes the transport swappable (CLAUDE.md RULE 1) — bind a different `HttpClient` here
// and every route in the app follows, with no edits anywhere else.

import { httpClient, type Method, type RequestConfig } from "./client";

export function request<T>(
  method: Method,
  url: string,
  body?: unknown,
  config?: RequestConfig,
): Promise<T> {
  return httpClient.send<T>(method, url, body, config);
}

export type { Method, RequestConfig };
