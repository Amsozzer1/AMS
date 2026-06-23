# hardware

Physical design for modules, the per-printer hub, and clusters. BOM and rationale live in
[docs/08-hardware.md](../docs/08-hardware.md); this folder holds the actual files.

```
cad/      Printable parts — module body, spool enclosure (+ rewind tension), Y-hub mount, ESP32/driver mounts
wiring/   Cluster wiring diagrams — ESP32 + TMC2209 ×N, shared step/dir + enable, common ground, 24V rail
bom/      Bills of materials (per-module, per-cluster, one-time)
```

## Reminders baked into the design (from docs/08)
- **One motor at a time** → cheap electronics (shared step/dir + enable select), tiny power, low heat.
- **24 V** wall-powered rail; **no batteries**. Breadboard is bench-learning only — real power
  rail = screw terminals / distribution block / small PCB.
- **Common ground:** tie the 24 V supply's (−) to the ESP32 GND.
- You own Bambu printers → **3D-print** most mechanical parts.

> Empty at scaffold time. First parts come from the hardware on-ramp (H0–H3) once a single
> module is proven (see docs/07-v0-plan.md, open question #16 spool back-spin).
