# AMS-X Frontend

The operator UI for the AMS-X Brain: a live printer dashboard, a 3MF upload that
shows the planned material swaps, and — the v0 money-shot — the **human-swap
prompt panel** that turns "module 2: feed" into a one-click action.

It is a **thin client**. It only talks to the Brain's documented HTTP API
(`server/src/amsx/api/__init__.py`); no MQTT, no business logic, no Python.

## Stack

- **Next.js (App Router) + TypeScript** — one well-supported toolchain, a lockfile,
  nothing to wire up by hand.
- **No extra dependencies**: no UI kit, no state/data-fetching library. Live data
  uses the built-in `fetch` + a tiny `usePolling` hook. Styling is one plain
  `globals.css`. `package.json` stays tiny on purpose.

## Run

```bash
npm install
npm run dev      # http://localhost:3000
```

Production build / serve:

```bash
npm run build
npm run start
npm run lint
```

## API base URL

The UI reads the Brain's base URL from `NEXT_PUBLIC_API_BASE`
(default `http://127.0.0.1:8000`). To point at another host, copy `.env.example`
to `.env.local` and set it, e.g.:

```
NEXT_PUBLIC_API_BASE=http://casaos.local:8000
```

Start the Brain in simulate mode (no hardware) to develop against it:

```bash
cd ../server && AMSX_PORT=8088 uv run amsx
# then run the UI with NEXT_PUBLIC_API_BASE=http://127.0.0.1:8088
```

## What the UI shows

- **Prompt panel** (top, highlighted) — polls `GET /api/prompts` ~1.5s; each
  pending `{ id, module_id, message }` is rendered prominently with a one-click
  **Done** that POSTs `/api/prompts/{id}/answer`.
- **Printer cards** — polls `GET /api/printers` ~2s: id, stage, filament sensor,
  loaded filament, progress. Click a card to open its detail view.
- **Printer detail** (`/printers/[id]`) — polls
  `GET /api/printers/{id}/detail` ~1.5s. A curated section surfaces the
  operationally-meaningful fields (connection/simulate, stage, progress &
  remaining time, nozzle/bed/chamber temps, fan speeds, wifi, model/serial/ip,
  loaded filament, and any non-empty `hms` health messages). Below it, the
  COMPLETE `raw` report renders as a recursive collapsible key/value tree so
  nothing the Brain knows is hidden. In simulate mode `raw` is sparse/empty
  until a report is fed.
- **Job upload** — pick a printer + a sliced `.gcode.3mf`, POST to
  `/api/printers/{id}/job`, render the returned `planned_swaps`; a bad file shows
  the server's 400 message.

## Later enhancement

Live state is currently **polled**. The Brain plans a websocket live-state channel
(see `docs/03-tech-stack.md`: "FastAPI + websockets for live state"); swapping the
polling hook for that channel is a documented future enhancement and is not needed
for v0.
