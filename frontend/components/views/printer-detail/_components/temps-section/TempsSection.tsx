import { str, temp, type PrintReport } from "../../_helpers";
import Field from "../field";

export default function TempsSection({ report }: { report: PrintReport }) {
  return (
    <section>
      <h2>Temperatures &amp; fans</h2>
      <div className="detail-grid">
        <Field label="nozzle">{temp(report.nozzle_temper, report.nozzle_target_temper)}</Field>
        <Field label="bed">{temp(report.bed_temper, report.bed_target_temper)}</Field>
        <Field label="chamber">{temp(report.chamber_temper, undefined)}</Field>
        <Field label="nozzle">
          {str(report.nozzle_diameter) ?? "—"} mm · {str(report.nozzle_type) ?? "—"}
        </Field>
        <Field label="cooling fan">{str(report.cooling_fan_speed) ?? "—"}</Field>
        <Field label="heatbreak fan">{str(report.heatbreak_fan_speed) ?? "—"}</Field>
        <Field label="aux fan 1">{str(report.big_fan1_speed) ?? "—"}</Field>
        <Field label="aux fan 2">{str(report.big_fan2_speed) ?? "—"}</Field>
      </div>
    </section>
  );
}
