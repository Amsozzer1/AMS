# Frontend — the API layer

> Serves [RULE 1](../rules/01-separation-of-concerns.md). Status: **built and in use.**

Everything that talks to the Brain goes through `frontend/api/`. Components call
`API.spools.create(body)` and learn nothing about URLs, HTTP verbs, or the client library.

## Files

| File | Its one job |
|---|---|
| `index.ts` | The public door. The only path anything outside `api/` may import. |
| `client.ts` | **The only file in the app that knows `fetch` exists.** Base URL, timeout, serialization, error mapping. |
| `request.ts` | The single verb routes are written against. Binds to the client. |
| `routes.ts` | **The only file with a URL or an HTTP verb.** |
| `types.ts` | Re-exports generated schemas, plus `ApiError` and UI-only types. |
| `types.generated.ts` | Generated from OpenAPI. **Never hand-edited.** |

## The transport seam

`client.ts` exports an `HttpClient` interface; `request.ts` depends on the interface, never on
`fetch`. Swapping to Axios — for interceptors, when auth lands — means adding a
`createAxiosClient` in `client.ts` and changing one export line. No route, component, or type
moves. That reversibility is the reason for the layering, not incidental to it.

## Types are generated, never written

`server/src/amsx/api/models.py` is the single source of truth. Types reach TypeScript by
generation, so they cannot drift from what the server actually sends.

```bash
cd frontend && npm run gen:api
```

That runs `server/scripts/dump_openapi.py` (imports the app directly — no server, no port, CI-safe)
then `openapi-typescript` over the result. **Re-run it after any change to `models.py`.**

`server/openapi.json` is a generated artifact and is gitignored.

## Rules

- Adding an endpoint is **one line in `routes.ts`** and nothing else.
- Never hand-write a server type. If a shape is wrong, fix `models.py` and regenerate.
- Every read takes an optional `RequestConfig` last — that is how `usePolling` threads its
  `AbortSignal` so unmounts cancel in-flight requests. Do not drop it.
- `FormData` bodies pass through untouched; the browser must set its own multipart boundary.
- `sim.*` is simulate-mode-only and hard-gated server-side. It is grouped separately so that
  stays obvious at the call site too.
