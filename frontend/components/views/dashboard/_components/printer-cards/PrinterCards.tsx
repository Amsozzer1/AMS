"use client";

import { API } from "@/api";
import { POLL_MS } from "@/constants";
import { usePolling } from "@/hooks";
import PrinterCard from "./_components/printer-card";

export default function PrinterCards() {
  const { data, error, loading } = usePolling(
    (signal) => API.printers.list({ signal }),
    POLL_MS.PRINTERS,
  );
  const printers = data ?? [];
  const empty = printers.length === 0;

  return (
    <section>
      <div className="section-head">
        <h2>Printers</h2>
        {!empty && <span className="count">{printers.length} connected</span>}
      </div>

      {error && empty && <div className="error">Could not reach the Brain: {error}</div>}

      {!error && loading && empty && (
        <div className="cards">
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      )}

      {!loading && !error && empty && (
        <div className="empty">No printers reported by the Brain.</div>
      )}

      {!empty && (
        <div className="cards">
          {printers.map((p) => (
            <PrinterCard key={p.id} p={p} />
          ))}
        </div>
      )}
    </section>
  );
}
