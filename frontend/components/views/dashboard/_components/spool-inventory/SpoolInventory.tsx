"use client";

// Every spool the Brain knows about (Spoolman or the fake store), with inline CRUD.
//
// Soft by design: Spoolman may be down or unconfigured, so an error or an empty list shows a
// calm empty state and the rest of the dashboard keeps working.

import { useCallback, useState } from "react";
import { API } from "@/api";
import { POLL_MS } from "@/constants";
import { usePolling } from "@/hooks";
import SpoolRow from "./_components/spool-row";
import AddSpoolForm from "./_components/add-spool-form";

export default function SpoolInventory() {
  const { data, error, loading, refresh } = usePolling(
    (signal) => API.spools.list(false, { signal }),
    POLL_MS.INVENTORY,
  );
  const spools = (data ?? []).filter((s) => !s.archived);
  const [showAdd, setShowAdd] = useState(false);

  const onAdded = useCallback(() => {
    setShowAdd(false);
    refresh();
  }, [refresh]);

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Spool inventory</h3>
        <div className="panel-head-actions">
          {spools.length > 0 && <span className="count">{spools.length}</span>}
          <button
            className="btn spool-add-toggle"
            type="button"
            onClick={() => setShowAdd((v) => !v)}
            aria-expanded={showAdd}
          >
            {showAdd ? "Cancel" : "+ Add spool"}
          </button>
        </div>
      </div>

      {showAdd && <AddSpoolForm onSuccess={onAdded} onCancel={() => setShowAdd(false)} />}

      {loading && spools.length === 0 && !error ? (
        <p className="mapping-sub">Loading inventory…</p>
      ) : error ? (
        <div className="empty">Inventory unavailable — Spoolman may be down or unconfigured.</div>
      ) : spools.length === 0 ? (
        <div className="empty">No spools in inventory.</div>
      ) : (
        <div className="spool-list">
          {spools.map((s) => (
            <SpoolRow key={s.id} s={s} onRefresh={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}
