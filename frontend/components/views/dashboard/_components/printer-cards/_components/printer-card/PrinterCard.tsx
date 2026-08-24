import Link from "next/link";
import type { PrinterState } from "@/api";
import { clampPct } from "@/utils";
import { stageClass } from "../../_helpers";

/** One printer at a glance, linking to its detail view. A paused printer gets the `attn`
 *  treatment — it is the state an operator has to act on. */
export default function PrinterCard({ p }: { p: PrinterState }) {
  const loaded = p.loaded_filament;
  const percent = clampPct(p.progress?.percent);
  const layer = p.progress?.layer;
  const paused = !!p.pause_reason;

  return (
    <Link
      href={`/printers/${encodeURIComponent(p.id)}`}
      className={`card card-link${paused ? " attn" : ""}`}
    >
      <div className="card-head">
        <span className="pid">{p.id}</span>
        <span className={`stage-badge ${stageClass(p.stage, paused)}`}>
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
