"use client";

import { useCallback, useEffect, useState } from "react";
import { API, type LoadoutRow, type Spool } from "@/api";
import { swatchColor } from "@/utils";

/** One printer's module→spool rows, each reassignable from the inventory.
 *
 *  Soft by design: if the store is down the picker stays empty and the row shows a calm
 *  message. Nothing here is allowed to crash the dashboard. */
export default function PrinterLoadout({
  printerId,
  spools,
}: {
  printerId: string;
  spools: Spool[];
}) {
  const [rows, setRows] = useState<LoadoutRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busyModule, setBusyModule] = useState<string | null>(null);

  const load = useCallback(
    (signal?: AbortSignal) =>
      API.printers.loadout
        .get(printerId, { signal })
        .then((r) => {
          setRows(r);
          setError(null);
        })
        .catch((err) => {
          if (signal?.aborted) return;
          setError(err instanceof Error ? err.message : String(err));
        })
        .finally(() => setLoaded(true)),
    [printerId],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const onAssign = useCallback(
    async (module: string, spoolId: string) => {
      if (!spoolId) return;
      setBusyModule(module);
      try {
        await API.printers.loadout.set(printerId, module, spoolId);
        await load();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusyModule(null);
      }
    },
    [printerId, load],
  );

  if (!loaded) return <p className="mapping-sub">Loading {printerId} loadout…</p>;
  if (error && rows.length === 0) {
    return <div className="empty">Loadout unavailable for {printerId}.</div>;
  }
  if (rows.length === 0) {
    return <div className="empty">No modules configured for {printerId}.</div>;
  }

  return (
    <div className="loadout-list">
      {rows.map((r) => {
        const s = r.spool;
        return (
          <div key={r.module} className="loadout-row">
            <span className="mod-id">{r.module}</span>
            <span className="loaded">
              <span
                className="swatch"
                style={{ background: swatchColor(s?.color_hex) }}
                aria-hidden
              />
              <span className="nm">{s ? s.name || s.material || s.id : "empty"}</span>
            </span>
            <select
              className="loadout-select"
              value={s?.id ?? ""}
              disabled={busyModule === r.module || spools.length === 0}
              onChange={(e) => onAssign(r.module, e.target.value)}
              aria-label={`Spool for ${r.module}`}
            >
              <option value="">— pick spool —</option>
              {spools.map((sp) => (
                <option key={sp.id} value={sp.id}>
                  {sp.name || sp.material || sp.id}
                </option>
              ))}
            </select>
          </div>
        );
      })}
    </div>
  );
}
