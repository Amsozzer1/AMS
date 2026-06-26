"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getLoadout,
  listPrinters,
  listSpools,
  setLoadout,
  type LoadoutRow,
  type Spool,
} from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

// =============================================================================
// Loadout — per printer, each configured module and the spool loaded into it.
// The operator can reassign a module's spool from the inventory via an inline
// picker (PUT /loadout). Soft: if the store is down the picker stays empty and
// the panel shows a calm message; nothing here crashes the dashboard.
// =============================================================================

const PRINTERS_POLL_MS = 5000;

function swatchColor(hex: string | null): string {
  if (hex && /^[0-9a-fA-F]{6}$/.test(hex)) return `#${hex}`;
  return "#9b948333";
}

function PrinterLoadout({
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
      getLoadout(printerId, signal)
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
        await setLoadout(printerId, module, spoolId);
        await load();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusyModule(null);
      }
    },
    [printerId, load],
  );

  if (!loaded) {
    return <p className="mapping-sub">Loading {printerId} loadout…</p>;
  }
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
                style={{ background: swatchColor(s?.color_hex ?? null) }}
                aria-hidden
              />
              <span className="nm">
                {s ? s.name || s.material || s.id : "empty"}
              </span>
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

export default function LoadoutPanel() {
  const { data: printerData } = usePolling(listPrinters, PRINTERS_POLL_MS);
  const printers = printerData ?? [];
  const [spools, setSpools] = useState<Spool[]>([]);

  // Inventory feeds every printer's picker; one shared soft load.
  useEffect(() => {
    const controller = new AbortController();
    listSpools(controller.signal)
      .then((s) => setSpools(s.filter((x) => !x.archived)))
      .catch(() => setSpools([]));
    return () => controller.abort();
  }, []);

  if (printers.length === 0) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h3>Module loadout</h3>
        </div>
        <div className="empty">No printers reported.</div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Module loadout</h3>
        <span className="count">{printers.length} printer{printers.length === 1 ? "" : "s"}</span>
      </div>
      {printers.map((p) => (
        <div key={p.id} style={{ marginTop: "var(--s-3)" }}>
          {printers.length > 1 && (
            <div className="mapping-sub mono" style={{ margin: "0 0 var(--s-2)" }}>
              {p.id}
            </div>
          )}
          <PrinterLoadout printerId={p.id} spools={spools} />
        </div>
      ))}
    </div>
  );
}
