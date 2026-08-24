import type { PrinterDetail } from "@/api";
import { clampPct } from "@/utils";
import { minutes, num, str, type PrintReport } from "../../_helpers";
import Field from "../field";

/** Print progress. Percent and layer prefer the printer's own report and fall back to the
 *  Brain's modelled `progress` — the report is fresher, the model is always present. */
export default function ProgressSection({
  d,
  report,
}: {
  d: PrinterDetail;
  report: PrintReport;
}) {
  const percent = clampPct(d.progress?.percent ?? num(report.mc_percent));
  const layer = num(report.layer_num) ?? d.progress?.layer ?? null;
  const totalLayer = num(report.total_layer_num);

  return (
    <section>
      <h2>Progress</h2>
      <div className="detail-grid">
        <Field label="percent">{percent !== null ? `${percent}%` : "—"}</Field>
        <Field label="layer">
          {layer !== null ? `${layer}${totalLayer ? ` / ${totalLayer}` : ""}` : "—"}
        </Field>
        <Field label="time remaining">{minutes(report.mc_remaining_time)}</Field>
        <Field label="subtask">{str(report.subtask_name) || "—"}</Field>
        <Field label="gcode file">{str(report.gcode_file) || "—"}</Field>
      </div>
      <div className="progress" style={{ marginTop: 12 }}>
        <span style={{ width: `${percent ?? 0}%` }} />
      </div>
    </section>
  );
}
