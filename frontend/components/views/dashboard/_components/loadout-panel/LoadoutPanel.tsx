"use client";

// Per printer: each configured module and the spool loaded into it, reassignable inline.

import { useEffect, useState } from "react";
import { API, type Spool } from "@/api";
import { POLL_MS } from "@/constants";
import { usePolling } from "@/hooks";
import PrinterLoadout from "./_components/printer-loadout";

export default function LoadoutPanel() {
  const { data } = usePolling((signal) => API.printers.list({ signal }), POLL_MS.INVENTORY);
  const printers = data ?? [];
  const [spools, setSpools] = useState<Spool[]>([]);

  // Inventory feeds every printer's picker — one shared soft load.
  useEffect(() => {
    const controller = new AbortController();
    API.spools
      .list(false, { signal: controller.signal })
      .then((s) => setSpools(s.filter((x) => !x.archived)))
      .catch(() => setSpools([]));
    return () => controller.abort();
  }, []);

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Module loadout</h3>
        {printers.length > 0 && (
          <span className="count">
            {printers.length} printer{printers.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {printers.length === 0 ? (
        <div className="empty">No printers reported.</div>
      ) : (
        printers.map((p) => (
          <div key={p.id} style={{ marginTop: "var(--s-3)" }}>
            {printers.length > 1 && (
              <div className="mapping-sub mono" style={{ margin: "0 0 var(--s-2)" }}>
                {p.id}
              </div>
            )}
            <PrinterLoadout printerId={p.id} spools={spools} />
          </div>
        ))
      )}
    </div>
  );
}
