"use client";

import Link from "next/link";
import { listPrinters, type PrinterState } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

const POLL_MS = 2000;

// progress is a best-effort dict { layer?, percent?, line? } — `percent` may be
// absent (e.g. when idle). Clamp to 0..100 for the bar; null when unknown.
function pct(progress: PrinterState["progress"]): number | null {
  const v = progress?.percent;
  if (typeof v !== "number") return null;
  return Math.max(0, Math.min(100, Math.round(v)));
}

function PrinterCard({ p }: { p: PrinterState }) {
  const loaded = p.loaded_filament;
  const percent = pct(p.progress);
  const layer = p.progress?.layer;
  return (
    <Link
      href={`/printers/${encodeURIComponent(p.id)}`}
      className="card card-link"
    >
      <div className="card-head">
        <span className="pid">{p.id}</span>
        <span className="stage-badge">{p.stage}</span>
      </div>

      {p.pause_reason && (
        <div className="row">
          <span className="k">paused</span>
          <span>{p.pause_reason}</span>
        </div>
      )}

      <div className="row">
        <span className="k">filament sensor</span>
        <span className={p.filament_sensor ? "sensor-on" : "sensor-off"}>
          {p.filament_sensor ? "present" : "absent"}
        </span>
      </div>

      <div className="row">
        <span className="k">loaded filament</span>
        <span>
          {loaded ? (
            <>
              <span
                className="swatch"
                style={{ background: loaded.color || "#888" }}
              />
              {loaded.material} #{loaded.index}
            </>
          ) : (
            "—"
          )}
        </span>
      </div>

      <div className="row">
        <span className="k">progress</span>
        <span>
          {percent !== null ? `${percent}%` : "—"}
          {typeof layer === "number" ? ` · layer ${layer}` : ""}
        </span>
      </div>
      <div className="progress">
        <span style={{ width: `${percent ?? 0}%` }} />
      </div>

      <span className="card-cta">View detail →</span>
    </Link>
  );
}

export default function PrinterCards() {
  const { data, error, loading } = usePolling(listPrinters, POLL_MS);
  const printers = data ?? [];

  return (
    <section>
      <h2>Printers</h2>
      {error && printers.length === 0 && (
        <div className="error">Could not reach the Brain: {error}</div>
      )}
      {!error && loading && printers.length === 0 && (
        <div className="prompt-empty">Loading…</div>
      )}
      {!loading && printers.length === 0 && !error && (
        <div className="prompt-empty">No printers reported.</div>
      )}
      <div className="cards">
        {printers.map((p) => (
          <PrinterCard key={p.id} p={p} />
        ))}
      </div>
    </section>
  );
}
