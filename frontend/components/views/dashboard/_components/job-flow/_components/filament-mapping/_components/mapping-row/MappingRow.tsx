import type { AssignRow } from "@/api";
import { gramsLabel, swatchColor } from "@/utils";

/** One print colour: its swatch, whether a module can feed it, and the module picker. */
export default function MappingRow({
  row,
  picked,
  gap,
  modules,
  onPick,
}: {
  row: AssignRow;
  picked: string;
  gap: boolean;
  modules: string[];
  onPick: (index: number, moduleId: string) => void;
}) {
  return (
    <div className={`map-row${gap ? " gap" : ""}`}>
      <span className="map-idx">{row.index}</span>

      <div className="map-colour">
        <span
          className="swatch-row"
          style={{ background: swatchColor(row.color_hex) }}
          aria-hidden
        />
        <span className="meta">
          <span className="mat">{row.material || "filament"}</span>
          <span className="grams">{gramsLabel(row.grams)}</span>
        </span>
      </div>

      <span className={`map-badge ${gap ? "gap" : "loaded"}`}>
        {gap ? "⚠ gap" : "✓ loaded"}
      </span>

      <select
        className="map-select"
        value={picked}
        onChange={(e) => onPick(row.index, e.target.value)}
        aria-label={`Module for filament ${row.index}`}
      >
        <option value="">— unassigned —</option>
        {modules.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </div>
  );
}
