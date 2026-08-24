import type { PrinterDetail } from "@/api";
import { num, str, type PrintReport } from "../../_helpers";
import Field from "../field";

/** Connection, identity, and the two facts that decide whether a swap can run: the printer's
 *  filament sensor and what the Brain believes is loaded. */
export default function StatusSection({
  d,
  report,
}: {
  d: PrinterDetail;
  report: PrintReport;
}) {
  const loaded = d.loaded_filament;
  return (
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
              <span className="swatch" style={{ background: loaded.color || "#888" }} />
              {loaded.material} #{loaded.index}
            </>
          ) : (
            "—"
          )}
        </Field>
      </div>
    </section>
  );
}
