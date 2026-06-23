# spikes — throwaway Phase-0 exploration (NOT shipped)

Per [docs/07-v0-plan.md](../docs/07-v0-plan.md): exploration is separate from the app. Write
throwaway scripts here to *discover* facts; once known, the **finding** moves into `server/`
(and a written MQTT command/field reference). Nothing here is production code.

## The v0.2 keystone spike (⛔ go/no-go for the whole project)
1. **Does external-spool multicolor pause-and-prompt?** (the `M400 U1` "No-AMS" preset) — top item.
2. **Filament-present sensor** — which report field, how reliable.
3. **Drive Bambu's change routine** over MQTT — unload / extrude / **confirm / resume** (Option A).
4. **Pause event** observable + matchable to the parsed plan.

## Parallel software spikes (no hardware)
- **3MF parse:** unzip a sliced `.gcode.3mf` → `Metadata/plate_1.gcode` → scan `M400 U1` / `M1020 S<n>`.
- **LAN job push:** FTPS upload + MQTT start.
- **Printer state model:** full-state-on-connect + incremental deltas against a real report stream.

> If item 1 or 3 fails → redesign before any hardware. See docs/05 #1–#3, #29.
