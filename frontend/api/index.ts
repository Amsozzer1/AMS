// The API module's public surface — the ONLY path anything outside `api/` may import from.
//
// Components import `{ API }` and the types they render. They never reach into `routes`,
// `request`, `client`, or `types.generated` directly: that is what keeps the internals (and
// the transport) free to change without touching a single component (CLAUDE.md RULE 1).

export { API } from "./routes";
export { API_BASE } from "./client";
export type { HttpClient, Method, RequestConfig } from "./client";
export * from "./types";
