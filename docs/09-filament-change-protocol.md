# 09 — Filament-Change Protocol & Job Ingestion (reference)

> Captures the research that **resolves open question #17** ("which filament is needed,
> when") and locks **Option A** (ride Bambu's own change routine). This is the factual
> backbone the orchestrator and job-parser are built on. Sources at the bottom.

## The core strategy: Option A — ride Bambu's built-in change routine (LOCKED)

We do **not** author custom hotend gcode. We use the printer's existing **manual
external-spool filament-change** flow and automate the human steps over MQTT.

| **Our side owns — filament logistics** | **Bambu owns — hotend physics** |
|----------------------------------------|----------------------------------|
| Remove old filament (retract past the hub) | Nozzle temperature management |
| Feed the right new filament to the printer's entry/sensor | Retract-from-melt-zone, load-to-nozzle |
| Decide *which* module, *when* | Purge, wipe, reposition, resume |

**The seam between them is the printer's existing change routine; we just drive its prompts
over MQTT.** Rationale: gcode is painful, it's already solved, and purge/retract amounts are
a per-nozzle × per-material calibration nightmare we refuse to own.

## Multi-color WITHOUT an AMS is a real, established workflow

In Bambu Studio you can slice a multi-color print for a bare external spool:
1. Set the printer preset's **"Change filament G-code"** to the **pause** command
   (`M400 U1`).
2. Save it as a **"No-AMS"** user preset.
3. Assign colors/filaments **as if** you had an AMS, with that preset selected.

The slicer then inserts a **pause at every color change**, and the printer stops and waits
for a manual swap. Community gcode "color-swap patchers" automate exactly this — so the
slicing path we depend on **exists and is proven**.

## A sliced 3MF is just a zip — here's what we parse

`*.gcode.3mf` → unzip →
```
Metadata/plate_1.gcode      ← the actual gcode the printer runs   (WE PARSE THIS)
Metadata/plate_1.json       ← plate metadata
Metadata/slice_info.config  ← filament / slice info
```
"Server parses the 3MF" = **unzip + read `plate_1.gcode`.** No custom slicer.
⚠️ This requires a **sliced** 3MF (it carries the gcode). An unsliced *project* 3MF would
have to be sliced first (OrcaSlicer-headless) — see #24/#28.

## How changes — and *which filament* — are encoded

| Command | Meaning |
|---------|---------|
| `M400 U1` | **Pause** and wait for manual filament change (the no-AMS trigger) |
| `M1020 S0 / S1 / S2 …` | **Which project filament is next** (`S0`=filament 1, `S1`=#2, …) ← the literal "which color" signal |
| `M620 S<n>A` / `M621` | AMS load / unload slot n (AMS-mode equivalents) |
| `M622 J1` / `M623` | wait-for / pause-for color swap |

The full sequence of changes **and the filament index at each** is in `plate_1.gcode`, in
order. The parser reads it top-to-bottom and emits an ordered plan.

## How this resolves #17

1. **Parse:** unzip → read `plate_1.gcode` → ordered **plan**:
   `[change#1 → filament 2, change#2 → filament 5, …]`.
2. **Map:** filament index → module (config now; Spoolman later).
3. **Trigger:** the live `M400 U1` pause (seen over MQTT) fires the swap; the server matches
   it to the next expected change in its plan → knows which module to feed.
4. **Validate:** see below.

This is the **hybrid model**, fully grounded: **plan from parsed gcode, trigger from live
pause.**

## Pause validation — "put an ID on the pauses we care about"

**We control the "Change filament G-code" preset** (the server prepares the job), so we can
make every pause we care about **uniquely tagged/numbered** (e.g. emit `M1020 S<n>` and/or
our own marker alongside `M400 U1`). Therefore:

- Pauses the server acts on are **pauses the server authored** — tagged, numbered, ours.
- A random **user** pause carries no marker → the server treats it as an **exception**
  (hold, alert), never a swap.
- A **state machine** owns "am I mid-swap" so stray events can't double-trigger.

> Rule: **the server only acts on a pause it can match to its own plan.** Everything else is
> handled safely (single-brain principle — the Pi handles every exception).

## Resume state — owned by the printer, with quality dials on our side

Because we ride the routine (Option A), the printer handles temp/load/purge/wipe/resume. The
things that still matter:

- **Temperature:** nozzle must be hot to retract, at the new material's temp to load. Long
  pauses may drop to standby → re-heat-and-wait. **Scope v0 to same-material, multi-*color***
  (e.g. all PLA) to delete the temperature variable. Mixed-material is later.
- **Ooze/blob:** a hot paused nozzle oozes; longer pause = worse. **Swap speed is a quality
  lever** — human-paced v0 transitions will look worse than the motorized version; that's
  expected and fine (it proves *function*).
- **Purge / color bleed:** new filament must push old fully out; if transitions look muddy,
  the fix is "purge more" — a tunable, not a wall.
- **Filament-position desync:** avoided **by** riding the routine (we only act in the
  windows it hands us; we never double-retract or fight its moves).
- **Confirm/resume gate (load-bearing):** the routine waits for confirmation; **we must be
  able to send unload/extrude/resume over MQTT** or the print sits paused forever.

## Still UNVERIFIED — goes on the v0.2 keystone spike

The gcode-level facts above are solid. What can't be confirmed from outside:
1. Does **external-spool multicolor actually pause-and-prompt** on a real print? *(top item)*
2. Does the **live MQTT report** surface that pause (and distinguish it / expose progress)
   so we can match it to the plan in real time?
3. Can we **drive unload / extrude / confirm / resume over MQTT** (note the UI quirk:
   `M400 U1` shows "paused by user," manual flow = cancel-prompt → filament menu → swap →
   resume)?

If #1 is false, that's a redesign trigger (we'd have to inject pauses differently) — which is
exactly why we test it first, before hardware.

## Try it yourself (fastest way to de-mystify)
Slice a small 2-color model with the **No-AMS / `M400 U1`** preset, open the `.gcode.3mf`
as a zip, read `Metadata/plate_1.gcode`, and search for `M400 U1`, `M1020 S`, `M620`/`M621`.
You'll see the ordered change list with filament numbers — the server's input, with your own
eyes.

## Sources
- [Multicolor prints without AMS, the easy(ish) way — Bambu forum](https://forum.bambulab.com/t/multicolor-prints-without-ams-the-easy-ish-way/242386)
- [G-Code Color Swap Patcher (Midlayer Filament Swapper)](https://press-ntr.github.io/Midlayer-Filament-Swapper/)
- [Bambu A1 filament-change gcode — M1020 S details](https://github.com/avatorl/bambu-a1-g-code/blob/main/change-filament/README.md)
- [Reading G-code for Bambu/Orca — M-code cheat sheet (M620–M623)](https://www.42prints.com/blog/reading-gcode-bambu-orca)
- [Integrating Spoolman with Bambu printers (MQTT/LAN)](https://www.mrkirby153.com/post/2025/05/bambu-spoolman/)
