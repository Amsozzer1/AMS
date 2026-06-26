# AMS-X Frontend

The operator UI for the AMS-X Brain: a live printer dashboard, a 3MF job intake
that shows the planned material swaps, the live swap-loop status, and — the v0
money-shot — the **Action Console** that turns "module 2: feed" into one
deliberate, satisfying hold-to-confirm action.

It is a **thin client**. It only talks to the Brain's documented HTTP API
(`server/src/amsx/api/__init__.py`); no MQTT, no business logic, no Python. Every
decision stays server-side (single-brain).

## Stack

- **Next.js 15 (App Router) + React 19 + TypeScript** — one well-supported
  toolchain with a lockfile, nothing to wire up by hand.
- **No UI kit / no data library.** Live data uses the built-in `fetch` + a tiny
  `usePolling` hook (`lib/usePolling.ts`). Styling is one hand-built design
  system in `app/globals.css`. The only added deps are Google fonts loaded via
  `next/font` (Space Grotesk, IBM Plex Mono, Inter) — no runtime requests.

## Run

```bash
npm install
npm run dev      # http://localhost:9000
```

Production build / serve / lint:

```bash
npm run build
npm run start    # http://localhost:9000
npm run lint
```

## API base URL

The UI reads the Brain's base URL from `NEXT_PUBLIC_API_BASE`
(default `http://127.0.0.1:9001`). To point at another host, copy `.env.example`
to `.env.local` and set it, e.g.:

```
NEXT_PUBLIC_API_BASE=http://casaos.local:9001
```

Start the Brain in simulate mode (no hardware) to develop against it. The Brain
defaults to :8000, so run it on :9001 to match the UI default:

```bash
cd ../server && AMSX_PORT=9001 uv run amsx
```

## Demo the prompt loop without hardware (simulate mode)

The hero is the human-swap loop. To exercise it end to end with no printer:

1. Upload a sliced `.gcode.3mf` in **Job intake** (this arms a plan).
2. `POST /api/printers/{id}/sim/pause` — the orchestrator advances to the next
   swap and raises a human prompt.
3. The **Action Console** lights up amber at the top of the page. Press & hold
   "mark done" (or focus it and press Enter) to POST the answer.
4. `POST /api/printers/{id}/sim/sensor?present=true` — closes the sensing step
   so the loop resumes.

Watch `GET /api/prompts` and `GET /api/printers/{id}/orchestrator` drive the UI.

## What the UI shows

- **Action Console** (top, the hero) — polls `GET /api/prompts` ~1s. When a
  prompt is pending the whole panel turns into an amber, beacon-striped call to
  action: the module rendered as a large physical address, the instruction, and
  one **press-and-hold** confirm that POSTs `/api/prompts/{id}/answer` and
  resumes the print. Idle, it sits as a quiet "standing by" strip. `aria-live`
  announces arrivals to screen readers.
- **Swap strip** — per armed printer, polls
  `GET /api/printers/{id}/orchestrator` ~1s: "Swap N of M", a row of swap pips
  with the current one highlighted, the live `swap_state`, and any `held`/`alerts`
  surfaced as an explicit error state (never decoration).
- **Printer cards** — polls `GET /api/printers` ~1s: id, stage (colored by
  state), loaded filament as a real **color swatch**, filament-sensor state, and
  progress. Click a card to open its detail view.
- **Printer detail** (`/printers/[id]`) — polls
  `GET /api/printers/{id}/detail` ~1.5s. A curated section (connection, stage,
  progress & remaining time, temps, fans, wifi, identity, loaded filament, any
  `hms` health messages) over the COMPLETE `raw` report as a recursive
  collapsible tree (`JsonTree`) so nothing the Brain knows is hidden.
- **Job intake** — drag/drop or browse a sliced `.gcode.3mf`, POST to
  `/api/printers/{id}/job`, render the ordered `planned_swaps`. **Arm only**
  posts `?start=false` to stage the plan without starting the print (the operator
  starts it from Bambu Studio). A bad file shows the server's 400 message.

## Design direction

Calm industrial control-room telemetry — a control surface for a machine that
swaps filament, where **color is data**, not decoration. Cold-steel slate ground
(`#0c1015`) with a faint engineering grid; a fixed signal palette encodes state
(cyan `#38bdf8` = live, green `#34d399` = ok/done, red `#fb6a6a` = fault) and one
warm amber channel (`#ffb13c`) is reserved **exclusively** for the action prompt,
so it can never be confused with ambient telemetry. Type: Space Grotesk
(display), IBM Plex Mono (telemetry readouts), Inter (body). Motion is sparing
and purposeful (the console arriving, the hold-to-confirm fill) and fully
disabled under `prefers-reduced-motion`.

## Later enhancement

Live state is currently **polled**. The Brain plans a websocket live-state
channel (see `docs/03-tech-stack.md`: "FastAPI + websockets for live state");
swapping the polling hook for that channel is a documented future enhancement and
is not needed for v0.
