"use client";

// Drill-in detail for one printer. Shows a curated, operationally-meaningful
// summary at the top, then the COMPLETE `raw` report below via JsonTree so
// nothing the Brain knows is hidden. Polls the detail endpoint so values update
// in place. Thin client: renders server state only, no business logic.

import { useCallback } from "react";
import Link from "next/link";
import { getPrinterDetail, type JsonValue, type PrinterDetail } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import JsonTree from "./JsonTree";

const POLL_MS = 1500;

// `raw.print` carries the status scalars + nested objects. Read defensively:
// shape is printer/firmware dependent and may be sparse (e.g. simulate mode).
type PrintReport = { [key: string]: JsonValue };

function printReport(d: PrinterDetail): PrintReport {
  const p = d.raw?.print;
  return p && typeof p === "object" && !Array.isArray(p) ? p : {};
}

function num(v: JsonValue | undefined): number | null {
  return typeof v === "number" ? v : null;
}

function str(v: JsonValue | undefined): string | null {
  if (typeof v === "string") return v;
  if (typeof v === "number") return String(v);
  return null;
}

function temp(cur: JsonValue | undefined, target: JsonValue | undefined): string {
  const c = num(cur);
  const t = num(target);
  if (c === null) return "—";
  const cTxt = `${Math.round(c)}°C`;
  return t && t > 0 ? `${cTxt} → ${Math.round(t)}°C` : cTxt;
}

function clampPct(v: number | null | undefined): number | null {
  if (typeof v !== "number") return null;
  return Math.max(0, Math.min(100, Math.round(v)));
}

function minutes(v: JsonValue | undefined): string {
  const m = num(v);
  if (m === null || m <= 0) return "—";
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return h > 0 ? `${h}h ${mm}m` : `${mm}m`;
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="detail-field">
      <span className="detail-field-k">{label}</span>
      <span className="detail-field-v">{children}</span>
    </div>
  );
}

// hms entries are health/error codes — shape varies by firmware, so render
// generically but surface them prominently.
function hmsMessages(report: PrintReport): JsonValue[] {
  const hms = report.hms;
  return Array.isArray(hms) ? hms : [];
}

export default function PrinterDetailView({ id }: { id: string }) {
  const fetcher = useCallback(
    (signal: AbortSignal) => getPrinterDetail(id, signal),
    [id],
  );
  const { data, error, loading } = usePolling(fetcher, POLL_MS);

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

  const d = data;
  const report = printReport(d);
  const percent = clampPct(d.progress?.percent ?? num(report.mc_percent));
  const layer = num(report.layer_num) ?? d.progress?.layer ?? null;
  const totalLayer = num(report.total_layer_num);
  const loaded = d.loaded_filament;
  const hms = hmsMessages(report);

  return (
    <main className="container">
      <DetailHeader id={id} />

      {error && (
        <div className="error" style={{ marginBottom: 16 }}>
          Update failed (showing last known): {error}
        </div>
      )}

      {/* Health / error codes — most important, surfaced first when present. */}
      {hms.length > 0 && (
        <section>
          <h2>Health messages (hms)</h2>
          <div className="hms-list">
            {hms.map((h, i) => (
              <div key={i} className="hms-item">
                <code>{JSON.stringify(h)}</code>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2>Status</h2>
        <div className="detail-grid">
          <Field label="connection">
            <span className={d.connected ? "sensor-on" : "sensor-off"}>
              {d.connected ? "connected" : "disconnected"}
            </span>
            {d.simulate && <span className="tag-sim">simulate</span>}
            {!d.seeded && <span className="tag-warn">no report yet</span>}
          </Field>
          <Field label="stage">
            <span className="stage-badge">{d.stage}</span>
          </Field>
          <Field label="gcode state">{str(report.gcode_state) ?? "—"}</Field>
          {d.pause_reason && (
            <Field label="pause reason">
              <span className="tag-warn">{d.pause_reason}</span>
            </Field>
          )}
          <Field label="print error">
            {num(report.print_error) ? (
              <span className="sensor-off">{str(report.print_error)}</span>
            ) : (
              "none"
            )}
          </Field>

          <Field label="model">{d.model}</Field>
          <Field label="serial">{d.serial}</Field>
          <Field label="ip">{d.ip ?? "—"}</Field>
          <Field label="wifi signal">{str(report.wifi_signal) ?? "—"}</Field>
          <Field label="speed level">{str(report.spd_lvl) ?? "—"}</Field>

          <Field label="filament sensor">
            <span className={d.filament_sensor ? "sensor-on" : "sensor-off"}>
              {d.filament_sensor ? "present" : "absent"}
            </span>
          </Field>
          <Field label="loaded filament">
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
          </Field>
        </div>
      </section>

      <section>
        <h2>Progress</h2>
        <div className="detail-grid">
          <Field label="percent">{percent !== null ? `${percent}%` : "—"}</Field>
          <Field label="layer">
            {layer !== null
              ? `${layer}${totalLayer ? ` / ${totalLayer}` : ""}`
              : "—"}
          </Field>
          <Field label="time remaining">{minutes(report.mc_remaining_time)}</Field>
          <Field label="subtask">{str(report.subtask_name) || "—"}</Field>
          <Field label="gcode file">{str(report.gcode_file) || "—"}</Field>
        </div>
        <div className="progress" style={{ marginTop: 12 }}>
          <span style={{ width: `${percent ?? 0}%` }} />
        </div>
      </section>

      <section>
        <h2>Temperatures &amp; fans</h2>
        <div className="detail-grid">
          <Field label="nozzle">
            {temp(report.nozzle_temper, report.nozzle_target_temper)}
          </Field>
          <Field label="bed">
            {temp(report.bed_temper, report.bed_target_temper)}
          </Field>
          <Field label="chamber">{temp(report.chamber_temper, undefined)}</Field>
          <Field label="nozzle">
            {str(report.nozzle_diameter) ?? "—"} mm ·{" "}
            {str(report.nozzle_type) ?? "—"}
          </Field>
          <Field label="cooling fan">{str(report.cooling_fan_speed) ?? "—"}</Field>
          <Field label="heatbreak fan">
            {str(report.heatbreak_fan_speed) ?? "—"}
          </Field>
          <Field label="aux fan 1">{str(report.big_fan1_speed) ?? "—"}</Field>
          <Field label="aux fan 2">{str(report.big_fan2_speed) ?? "—"}</Field>
        </div>
      </section>

      <section>
        <h2>Raw report (everything)</h2>
        <p className="prompt-empty" style={{ marginBottom: 12 }}>
          The printer&apos;s complete own report. Click any object or array to
          expand.
        </p>
        <div className="raw-tree">
          <JsonTree data={(d.raw ?? {}) as { [k: string]: JsonValue }} />
        </div>
      </section>
    </main>
  );
}

function DetailHeader({ id }: { id: string }) {
  return (
    <header className="app-header">
      <div>
        <Link href="/" className="back-link">
          ← Dashboard
        </Link>
        <h1 className="detail-title">
          Printer · <span className="mono">{id}</span>
        </h1>
      </div>
    </header>
  );
}
