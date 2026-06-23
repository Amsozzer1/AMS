# 08 — Hardware Shopping List

> Reference list. Quantities marked **×N** scale with the number of modules; everything else
> is one-time. Exact parts (voltage, which TMC, etc.) get pinned during the **H1** bench
> step, but this is enough to start buying. **Big advantage: you own Bambu printers, so most
> mechanical/mounting parts can be 3D-printed instead of bought.**

## Choices that shape this list
- **Stepper:** learn on a cheap geared motor; build real modules with **NEMA 17**.
- **Control (DECIDED):** **ESP32 (or Pico W) per cluster**, talking to the brain over **WiFi
  → MQTT** (same bus as the printers). One ESP32 drives ~16 modules. The Pi/brain decides;
  the ESP32 executes. (Plain Pico has **no WiFi** — it'd need a USB tether, so we use ESP32.)
- **Module grip:** a **BMG-style Bowden extruder** (dual drive gears + idler + tension in
  one unit) so you don't build a filament drive from scratch.
- **Motor voltage:** **24V** for the motor bus (quieter/stronger headroom than 12V).
- **One module moves at a time** → cheap electronics (shared step/dir + enable select), tiny
  power, low heat.

## Power & electrical fundamentals (read this — it kills two myths)
- **Power is the *easy* part.** A NEMA 17 *pushing filament* is low-power: ~0.3–0.6 A @ 24V
  ≈ **8–15 W while moving** (the "1.5 A" rating is internal coil current, not wall draw).
  Idle/disabled motors ≈ **0 W**. With one motor active per cluster, a **16-module cluster
  peaks at ~24 W**; a big 4-printer system ~**120 W total**.
- **A wall socket is ~1,800–2,400 W** — we use ~5%. **No batteries.** (A 9V battery can't even
  supply one stepper and would die in minutes.) Use a **wall-powered 24V DC supply**:
  24V/5A per cluster, 24V/10A for several.
- **A breadboard is for *bench learning only* (H0–H2).** It can't carry real motor power —
  contacts are ~1 A and loose. The real cluster power rail = **screw terminals / distribution
  block / small PCB** (3D-print the mounts).
- **Common ground (the #1 first-build gotcha):** voltage is always measured *relative to a
  reference (ground = 0V)*. The 24V motor supply and the ESP32's 3.3V logic must **share the
  same ground** or signals are meaningless. **Fix = one wire** from the 24V supply's **(−)**
  to the **ESP32 GND**. Keep the **+** sides separate; only the grounds join.

---

## 1. Core / brain (one-time)
> **DECIDED for now: the brain is the user's existing CasaOS device** — nothing to buy. It's
> Docker-native (run the server + Mosquitto broker as containers) and needs **no GPIO**
> (modules are network devices over WiFi/MQTT). Just keep it always-on and on the same LAN
> as the printers. The Pi option below is only if you ever want a dedicated box.

| Item (only if NOT using CasaOS) | Notes |
|------|-------|
| **Raspberry Pi 5 (4GB or 8GB)** | Runs server + web UI + MQTT broker (+ OrcaSlicer-headless if needed). 8GB if you'll slice on it. |
| **Official Pi 5 PSU (27W USB-C, 5V/5A)** | Pi 5 is picky about power; use the official one. |
| **microSD 32GB+ (A2)** *or* NVMe SSD + HAT | SD to start; SSD if you want speed/reliability. |
| **Active-cooling case / fan + heatsink** | Pi 5 throttles without it. |
| **Ethernet cable** | Wire the brain to the LAN; more reliable than WiFi for MQTT. |

## 2. Learning kit — H0–H3 (one-time, cheap, buy first)
This is the smallest cart to start the hardware on-ramp on the bench.
| Item | For |
|------|-----|
| **Breadboard + jumper wire kit (M-M, M-F, F-F)** | H0–H2 wiring |
| **LED + 220–330Ω resistors** | H0 (blink) |
| **28BYJ-48 stepper + ULN2003 driver board** (cheap kit) | H1 — learn stepper control safely (low power) |
| **Filament runout/presence sensor** (microswitch or optical module) | H2 — read presence |
| **Digital multimeter** | **Essential** for a beginner — power/continuity/debugging |
| **ESP32 dev board** + headers | H1+ — the real cluster controller (WiFi → MQTT) |
| **USB cable (ESP32 ↔ computer)** | For flashing firmware / bench testing |

## 3. One real module — Phase 1 BOM (×N to scale)
| Item | Qty/module | Notes |
|------|-----------|-------|
| **NEMA 17 stepper** (pancake or standard) | ×1 | The filament pusher. Pancake if space-tight. |
| **TMC2209 stepper driver** | ×1 | Silent, StallGuard (jam detect), UART config. |
| **BMG-style Bowden extruder** (dual-drive + idler) | ×1 | The grip mechanism. Pairs with the NEMA 17. |
| **Filament presence sensor** | ×1 | Local "filament present / empty" — optional but wanted. |
| **PTFE tube, 2mm ID / 4mm OD** | a few meters | The filament path. Buy a roll. |
| **PC4-M10 / PC4-M6 push-fit couplers + bulkheads** | several | Connect PTFE to extruder/hub/printer. |
| **Drive/idler bearings, springs, M3 fasteners** | a few | Often included with the extruder kit. |
| **JST/Dupont connectors + wire** | as needed | Motor + sensor wiring. |
| **3D-printed spool holder/enclosure + light tension** | ×1 | Holds the spool, **contains tangles, and adds rewind drag** so retract slack doesn't birds-nest (open #16). Print it. |

> The **ESP32 + a few TMC2209s** drive several modules, so the **ESP32 is per-cluster, not
> ×N** — roughly one ESP32 per ~16 modules. Drivers (TMC2209) **are** ×N.

## 4. Filament merge / hub (per printer)
| Item | Notes |
|------|-------|
| **Filament Y-connector / 2-to-1 (or 3-to-1) merger** | The "dumb hub." Off-the-shelf splitter **or** a 3D-printed manifold. ⚠️ Reliability of merge is open question #6 — start simple. |
| **PTFE + couplers from hub → printer external-spool input** | Goes **into the printer's external feed, not Bambu's AMS hub**. |

## 5. Power (one-time, sized to module count)
| Item | Notes |
|------|-------|
| **24V DC PSU** (e.g. 24V 5A to start; 10A+ for many modules) | Powers the steppers via the drivers. **Do not power motors from the Pi.** |
| **DC barrel/screw terminals, fused inlet** | Clean, safe power distribution. |
| **(Optional) buck converter 24V→5V** | If powering logic from the same supply. |

## 6. Tools (one-time)
| Item | Why |
|------|-----|
| **Multimeter** | (listed above) — non-negotiable for a beginner |
| **Soldering iron + solder** | You'll join wires/headers eventually |
| **Wire strippers + crimp tool + ferrules/Dupont crimps** | Clean connections |
| **Digital calipers** | Measuring filament path, fittings, printed parts |
| **Screwdrivers + hex/Allen keys** | Assembly |
| **(Have already) a Bambu printer** | Print mounts, the hub manifold, module frames — huge leverage |

## 7. Storage / frame (long-term, when scaling)
| Item | Notes |
|------|-------|
| **IKEA shelving unit** (your mentioned idea) | Houses ~30 modules |
| **3D-printed module mounts / spool holders** | Print these |
| **Cable management (raceways, ties)** | 30 modules = a lot of wiring |

---

## What to actually buy *now* (to start)
Just enough to begin v0's parallel hardware track without over-committing:
1. **Brain: nothing to buy** — using the existing **CasaOS** device.
2. **Learning kit** (section 2) — breadboard, LED/resistor, 28BYJ-48+ULN2003, a sensor,
   **multimeter**, an **ESP32**.
3. **One module's worth** of section 3 (NEMA 17, TMC2209, BMG extruder, PTFE roll, couplers,
   one sensor) — but you can defer this until H1 confirms the approach.

Everything else (24V PSU sizing, hub parts, second+ modules, shelving) waits until one
module works.

## Open hardware decisions (pin during H1)
- NEMA 17 exact spec (torque/length, pancake vs full) and **steps-per-mm** with the chosen gear.
- 24V PSU **amperage** sizing per cluster (the voltage itself is decided: 24V).
- TMC2209 confirmed vs A4988 fallback.
- **How many modules per ESP32** and the exact **shared step/dir + enable-select** scheme
  (incl. whether an I/O expander is needed for the enable lines) — see
  [05-open-questions.md](05-open-questions.md) #13/#15. *(Bus itself is decided: WiFi/MQTT.)*
- Off-the-shelf Y-merger vs printed manifold (open question #6/#7).
