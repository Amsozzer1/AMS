"use client";

// Drill-in detail for one printer: a curated, operationally-meaningful summary followed by
// the COMPLETE raw report, so nothing the Brain knows is hidden. Polls so values update in
// place. Thin client — renders server state only, no business logic.

import { useCallback } from "react";
import { API } from "@/api";
import { POLL_MS } from "@/constants";
import { usePolling } from "@/hooks";
import { hmsMessages, printReport } from "./_helpers";
import DetailHeader from "./_components/detail-header";
import HmsPanel from "./_components/hms-panel";
import StatusSection from "./_components/status-section";
import ProgressSection from "./_components/progress-section";
import TempsSection from "./_components/temps-section";
import RawSection from "./_components/raw-section";

export default function PrinterDetail({ id }: { id: string }) {
  const fetcher = useCallback(
    (signal: AbortSignal) => API.printers.detail(id, { signal }),
    [id],
  );
  const { data, error, loading } = usePolling(fetcher, POLL_MS.PRINTER_DETAIL);

  if (!data) {
    return (
      <main className="container">
        <DetailHeader id={id} />
        {error ? (
          <div className="error">Could not reach the Brain: {error}</div>
        ) : loading ? (
          <div className="prompt-empty">Loading…</div>
        ) : (
          <div className="prompt-empty">No data.</div>
        )}
      </main>
    );
  }

  const report = printReport(data);

  return (
    <main className="container">
      <DetailHeader id={id} />

      {/* A failed tick keeps the last good data on screen — say so rather than blanking it. */}
      {error && (
        <div className="error" style={{ marginBottom: 16 }}>
          Update failed (showing last known): {error}
        </div>
      )}

      <HmsPanel messages={hmsMessages(report)} />
      <StatusSection d={data} report={report} />
      <ProgressSection d={data} report={report} />
      <TempsSection report={report} />
      <RawSection raw={data.raw} />
    </main>
  );
}
