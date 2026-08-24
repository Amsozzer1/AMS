"use client";

// Step two of the job flow: the Bambu-Studio-style editable colour→module panel. Mounted
// only after an arm, so a one-shot load (not a poll) is the right shape. "Confirm & Start"
// persists the mapping then starts the already-armed job — never re-arms, which would wipe it.

import { useCallback, useEffect, useMemo, useState } from "react";
import { API, type AssignRow } from "@/api";
import { buildMapping, countGaps, isGap, pickedModule, seedChoices } from "./_helpers";
import MappingRow from "./_components/mapping-row";

export default function FilamentMapping({ printerId }: { printerId: string }) {
  const [rows, setRows] = useState<AssignRow[]>([]);
  const [confirmedServer, setConfirmedServer] = useState(false);
  const [modules, setModules] = useState<string[]>([]);
  const [choice, setChoice] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setStarted(false);
    setError(null);
    Promise.all([
      API.jobs.assignment.get(printerId, { signal: controller.signal }),
      API.printers.loadout.get(printerId, { signal: controller.signal }).catch(() => []),
    ])
      .then(([assignment, loadout]) => {
        setRows(assignment.rows);
        setConfirmedServer(assignment.confirmed);
        setModules(loadout.map((r) => r.module));
        setChoice(seedChoices(assignment.rows));
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

  const gapCount = useMemo(() => countGaps(rows, choice), [rows, choice]);

  const onConfirmStart = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await API.jobs.assignment.confirm(printerId, buildMapping(rows, choice));
      await API.jobs.start(printerId);
      setStarted(true);
      setConfirmedServer(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [printerId, rows, choice]);

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

  // Nothing armed for this printer — the panel stays invisible until there is a job to map.
  if (rows.length === 0) return null;

  return (
    <section>
      <div className="section-head">
        <h2>Filament mapping</h2>
        <span className="count mono">{printerId}</span>
      </div>

      <div className="mapping armed">
        <p className="mapping-sub">
          One row per print colour. Pick which module feeds each colour, then confirm &amp;
          start. Gap rows need a colour loaded into a module.
        </p>

        <div className="map-table">
          {rows.map((r) => (
            <MappingRow
              key={r.index}
              row={r}
              picked={pickedModule(r, choice)}
              gap={isGap(r, choice)}
              modules={modules}
              onPick={setRowModule}
            />
          ))}
        </div>

        <div className="mapping-actions">
          <button
            className="btn btn-primary"
            type="button"
            onClick={onConfirmStart}
            disabled={busy || started}
          >
            {busy ? "Starting…" : started ? "Started ✓" : "Confirm & Start"}
          </button>
          {gapCount > 0 && !started && (
            <span className="gap-note">
              {gapCount} colour{gapCount === 1 ? "" : "s"} still unmapped — load
              {gapCount === 1 ? " it" : " them"} into a module, but you can start anyway.
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
