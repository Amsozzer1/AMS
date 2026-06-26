"use client";

import Link from "next/link";
import { listPrinters, type PrinterState } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

const POLL_MS = 1000;

// progress is a best-effort dict { layer?, percent?, line? } — `percent` may be
// absent (e.g. when idle). Clamp to 0..100 for the bar; null when unknown.
function pct(progress: PrinterState["progress"]): number | null {
  const v = progress?.percent;
  if (typeof v !== "number") return null;
  return Math.max(0, Math.min(100, Math.round(v)));
}

// Map the free-text stage string onto a signal color class. The server stage
// vocabulary is open, so match on substrings and fall back to neutral.
function stageClass(stage: string, paused: boolean): string {
  const s = stage.toLowerCase();
  if (paused || s.includes("pause") || s.includes("swap")) return "stage-act";
  if (s.includes("error") || s.includes("fault") || s.includes("fail"))
    return "stage-fault";
  if (s.includes("run") || s.includes("print") || s.includes("working"))
    return "stage-run";
  return "stage-idle";
}

function PrinterCard({ p }: { p: PrinterState }) {
  const loaded = p.loaded_filament;
  const percent = pct(p.progress);
  const layer = p.progress?.layer;
  const paused = !!p.pause_reason;
  const sCls = stageClass(p.stage, paused);

  return (
    <Link
      href={`/printers/${encodeURIComponent(p.id)}`}
      className={`card card-link${paused ? " attn" : ""}`}
    >
      <div className="card-head">
        <span className="pid">{p.id}</span>
        <span className={`stage-badge ${sCls}`}>
          <span className="sdot" aria-hidden />
          {p.stage}
        </span>
      </div>

      <div className="telemetry">
        {paused && (
          <div className="row">
            <span className="k">paused</span>
            <span className="v" style={{ color: "var(--signal-act)" }}>
              {p.pause_reason}
            </span>
          </div>
        )}

        <div className="row">
          <span className="k">loaded filament</span>
          <span className="v">
            {loaded ? (
              <>
                <span
                  className="swatch"
                  style={{ background: loaded.color || "#888" }}
                  aria-hidden
                />
                {loaded.material} · idx {loaded.index}
              </>
            ) : (
              "—"
            )}
          </span>
        </div>

        <div className="row">
          <span className="k">filament sensor</span>
          <span className={`v ${p.filament_sensor ? "sensor-on" : "sensor-off"}`}>
            {p.filament_sensor ? "● present" : "○ absent"}
          </span>
        </div>
      </div>

      <div className="progress-wrap">
        <div className="progress-meta">
          <span className="pct">{percent !== null ? `${percent}%` : "idle"}</span>
          <span>{typeof layer === "number" ? `layer ${layer}` : "—"}</span>
        </div>
        <div className="progress">
          <span style={{ width: `${percent ?? 0}%` }} />
        </div>
      </div>

      <span className="card-cta">Open detail →</span>
    </Link>
  );
}

export default function PrinterCards() {
  const { data, error, loading } = usePolling(listPrinters, POLL_MS);
  const printers = data ?? [];

  return (
    <section>
      <div className="section-head">
        <h2>Printers</h2>
        {printers.length > 0 && (
          <span className="count">{printers.length} connected</span>
        )}
      </div>

      {error && printers.length === 0 && (
        <div className="error">Could not reach the Brain: {error}</div>
      )}

      {!error && loading && printers.length === 0 && (
        <div className="cards">
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      )}

      {!loading && printers.length === 0 && !error && (
        <div className="empty">No printers reported by the Brain.</div>
      )}

      {printers.length > 0 && (
        <div className="cards">
          {printers.map((p) => (
            <PrinterCard key={p.id} p={p} />
          ))}
        </div>
      )}
    </section>
  );
}
