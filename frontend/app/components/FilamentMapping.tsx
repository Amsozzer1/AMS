"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  confirmAssignment,
  getAssignment,
  getLoadout,
  startArmedJob,
  type AssignRow,
} from "@/lib/api";

// =============================================================================
// Filament mapping — the Bambu-Studio-style editable colour→module panel.
//
// After a job is uploaded with start=false the Brain arms it and computes a
// proposal: one row per print colour, each with the module the resolver guessed.
// We render that as an editable table — a real colour swatch, material + grams, a
// status badge (loaded / gap), and a module <select> per row. The operator can
// override any row, then "Confirm & Start" pushes the mapping and starts the
// already-armed job. Thin client: every decision is the operator's; the Brain
// owns the resolve + start.
// =============================================================================

// 6-hex RRGGBB → a CSS colour. Falls back to a neutral grey when unknown so a
// missing colour never renders as a broken swatch.
function swatchColor(hex: string | null): string {
  if (hex && /^[0-9a-fA-F]{6}$/.test(hex)) return `#${hex}`;
  return "#9b948333";
}

function grams(g: number | null): string {
  if (typeof g !== "number") return "—";
  return `${Math.round(g)} g`;
}

export default function FilamentMapping({ printerId }: { printerId: string }) {
  const [rows, setRows] = useState<AssignRow[]>([]);
  const [confirmedServer, setConfirmedServer] = useState(false);
  const [modules, setModules] = useState<string[]>([]);
  // Operator's local module choice per filament index (overrides the proposal).
  const [choice, setChoice] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  // Load the proposal + the printer's module ids. The mapping panel is only
  // mounted after an arm, so a one-shot load (not a poll) is the right shape.
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setStarted(false);
    setError(null);
    Promise.all([
      getAssignment(printerId, controller.signal),
      getLoadout(printerId, controller.signal).catch(() => []),
    ])
      .then(([assignment, loadout]) => {
        setRows(assignment.rows);
        setConfirmedServer(assignment.confirmed);
        setModules(loadout.map((r) => r.module));
        // Seed local choices from the proposal so unedited rows confirm as-is.
        const seed: Record<number, string> = {};
        for (const r of assignment.rows) {
          if (r.module) seed[r.index] = r.module;
        }
        setChoice(seed);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [printerId]);

  const setRowModule = useCallback((index: number, moduleId: string) => {
    setChoice((prev) => ({ ...prev, [index]: moduleId }));
  }, []);

  // A row is a gap if the resolver flagged it AND the operator hasn't picked a
  // module for it. Once a module is chosen it reads as resolvable.
  const gapCount = useMemo(
    () => rows.filter((r) => r.status === "gap" && !choice[r.index]).length,
    [rows, choice],
  );

  const onConfirmStart = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const mapping: Record<number, string> = {};
      for (const r of rows) {
        const m = choice[r.index] ?? r.module;
        if (m) mapping[r.index] = m;
      }
      await confirmAssignment(printerId, mapping);
      await startArmedJob(printerId);
      setStarted(true);
      setConfirmedServer(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [printerId, rows, choice]);

  // Nothing armed for this printer → render nothing (the panel is invisible
  // until there's a job to map).
  if (loading) {
    return (
      <section>
        <div className="section-head">
          <h2>Filament mapping</h2>
          <span className="count mono">{printerId}</span>
        </div>
        <div className="mapping">
          <p className="mapping-sub">Loading the armed job&rsquo;s colour plan…</p>
        </div>
      </section>
    );
  }

  if (rows.length === 0) return null;

  return (
    <section>
      <div className="section-head">
        <h2>Filament mapping</h2>
        <span className="count mono">{printerId}</span>
      </div>

      <div className="mapping armed">
        <p className="mapping-sub">
          One row per print colour. Pick which module feeds each colour, then
          confirm &amp; start. Gap rows need a colour loaded into a module.
        </p>

        <div className="map-table">
          {rows.map((r) => {
            const picked = choice[r.index] ?? r.module ?? "";
            const isGap = r.status === "gap" && !choice[r.index];
            return (
              <div key={r.index} className={`map-row${isGap ? " gap" : ""}`}>
                <span className="map-idx">{r.index}</span>

                <div className="map-colour">
                  <span
                    className="swatch-row"
                    style={{ background: swatchColor(r.color_hex) }}
                    aria-hidden
                  />
                  <span className="meta">
                    <span className="mat">{r.material || "filament"}</span>
                    <span className="grams">{grams(r.grams)}</span>
                  </span>
                </div>

                <span className={`map-badge ${isGap ? "gap" : "loaded"}`}>
                  {isGap ? "⚠ gap" : "✓ loaded"}
                </span>

                <select
                  className="map-select"
                  value={picked}
                  onChange={(e) => setRowModule(r.index, e.target.value)}
                  aria-label={`Module for filament ${r.index}`}
                >
                  <option value="">— unassigned —</option>
                  {modules.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
            );
          })}
        </div>

        <div className="mapping-actions">
          <button
            className="btn btn-primary"
            type="button"
            onClick={onConfirmStart}
            disabled={busy || started}
          >
            {busy
              ? "Starting…"
              : started
                ? "Started ✓"
                : "Confirm & Start"}
          </button>
          {gapCount > 0 && !started && (
            <span className="gap-note">
              {gapCount} colour{gapCount === 1 ? "" : "s"} still unmapped — load
              {gapCount === 1 ? " it" : " them"} into a module, but you can start
              anyway.
            </span>
          )}
          {started && (
            <span className="confirmed-note">
              Print started — watch the action console for swap prompts.
            </span>
          )}
          {confirmedServer && !started && !busy && (
            <span className="confirmed-note">Mapping already confirmed.</span>
          )}
        </div>

        {error && <div className="error">{error}</div>}
      </div>
    </section>
  );
}
