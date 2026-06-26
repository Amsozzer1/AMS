# AMS-X — Edge Cases (living doc)

Running list of every edge case raised while designing the Spoolman/mapping integration and the
swap pipeline. We resolve these *before* building so we know they exist. Companion to
`2026-06-25-spoolman-integration-design.md`.

**Status:** ✅ decided/resolved · 🔶 open (needs a decision) · ⏸ deferred (kept in the plan, built later)

---

## Job parsing / color plan

1. **Color-plan ↔ pause alignment** ✅ — colors come from `custom_gcode_per_layer.xml`, pauses from
   the gcode's `M400 U1`. Rule: **the `M400 U1` pauses are the spine**; attach color by **ordered
   position** (k-th pause = k-th `tool_change` entry), and **validate the counts match**. On
   mismatch → degrade to index-only prompts + warn. The operator also confirms the mapping before
   start, so a bad lineup is caught by a human too.
2. **Multiple changes on one layer** ✅ — bind by **ordinal/file order** (the cursor), never a
   layer→color dict (which would collapse two same-layer changes). Layer stays only a ±1 guard.
3. **Variable / adaptive layer height** ✅ — do **not** rely on `round(top_z / layer_height)` as the
   primary key; ordered position is primary. The layer guard tolerance absorbs drift.
4. **Non-color `M400 U1`** (operator-inserted pause to drop in a nut/magnet) 🔶 — a pause with no
   matching color change → count mismatch → degrade. Open: can we detect/skip it cleanly?
5. **Single-color print (no changes)** ✅ — no mapping, no swaps; just print.
6. **Missing / garbled metadata** ✅ — degrade to the index-only human prompt; never block.

## Spoolman / inventory

7. **Spoolman down or empty at start** ✅ — Spoolman is a **SOFT** dependency; printing NEVER blocks
   on it. Fallback: operator picks **backup modules**; we drive that module but don't name a color.
8. **Loadout ≠ physical reality** (wrong spool physically on a module) ✅ accepted — **user error,
   not ours.** Guarantee = "if m2 is mapped, we drive m2." No color verification (a camera + vision
   model is out of scope). The human-in-the-loop is the only check.
9. **Active set vs full catalog** ✅ — scope the *loaded* filaments via a Spoolman **location**
   (e.g. `"AMS"`, configurable): only spools in that location are "in the system." The mapping panel
   is the loadout.
10. **`ams_module` field already exists with a different type** 🔶 — validate on startup; use as-is
    or warn. (Spoolman forbids changing a field's type.)
11. **Needed color not in inventory** ✅ — gap → operator adds it in Spoolman or assigns a module
    anyway (no color guarantee).
12. **Consume on failure/cancel** ✅ accepted-approximate — best-effort `PUT /spool/{id}/use` on
    finish/cancel/fail; "close enough", inventory drift tolerated.
13. **Same spool serves multiple colors/rows** ✅ — allowed; consume **aggregates by spool**.
14. **Spoolman is external/user-run** ✅ — AMS-X stores a **configurable base URL** (frontend →
    backend → persisted); Spoolman is **not** in our repo (cloned dir is reference only → gitignore).
15. **Network timeout mid-operation** 🔶 — timeouts/retries + graceful degrade. Open.
16. **Same color, different material** (PLA white vs PETG white) ✅ — index-keying distinguishes them
    even though the UI swatch looks identical.

## Modules / loadout / swap

17. **Colors > modules** (e.g. 5 colors, 4 modules) 🔶 — requires a **mid-print module reload** flow.
    Needs resolution (the human can reload when prompted; define how the mapping expresses it).
18. **Spurious layer-0 start pause** 🔶 — intermittent; correctly safe-held, but the print then
    **sits paused** until resumed. Understand what it is; decide whether to auto-resume.
19. **Re-arm duplicate orchestrator** ✅ resolved — old orchestrator is unsubscribed on re-arm.
20. **Hot-reload drops the armed orchestrator** ✅ known — a fix can't retro-fire an already-held
    pause; verify on a fresh print.
21. **Print started outside AMS-X** (Bambu Studio / SD) ✅ — arm-only path (`start=false`); swap loop
    from the pause onward; no FTPS.
22. **Confirm & Start with an unresolved gap** 🔶 — block start, or warn-and-allow? Open.
23. **Mid-print mapping correction** 🔶 — can the operator fix a wrong mapping at a pause? (v0:
    pre-start only.) Open.
24. **Base color** ✅ — it's a **mappable row** like any other; the user assigns it. Pre-fill it from
    the printer's *current* external-spool filament (see #28) so we don't ask them to re-declare
    what's already loaded.
28. **Printer external-spool filament (`vt_tray`) state sync** ✅ CONFIRMED live — read
    `print.vt_tray` (`tray_color` RRGGBBAA, `tray_type`, `tray_info_idx`, temps) to seed/confirm the
    BASE; write on each swap via `ams_filament_setting` (`ams_id=255, tray_id=254, slot_id=0`).
    Verified on the A1 (set + restored). Caveat: the A1 NACKs nothing — read back to confirm.

## Deferred (kept in the plan, built later)

25. **Runout → backup spool** ⏸ — an AMS swaps on *runout*, not only color. Same filament on two
    modules (primary + backup); Bambu detects runout, we offer the backup. A color may then map to a
    primary **and** backup module.
26. **In-AMS-X inventory CRUD** ⏸ — manage Spoolman filaments/spools from the AMS-X UI (first cut is
    read + tag + consume).
27. **Standalone loadout / inventory screens** ⏸ — MVP is the per-job mapping panel; dedicated
    management screens come later.
