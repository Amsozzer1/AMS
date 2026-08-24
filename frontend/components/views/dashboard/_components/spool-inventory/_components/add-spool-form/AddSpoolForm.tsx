"use client";

import { useAddSpoolForm } from "./_helpers";
import TextField from "./_components/text-field";

export default function AddSpoolForm({
  onSuccess,
  onCancel,
}: {
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const f = useAddSpoolForm(onSuccess);

  return (
    <form className="spool-add-form" onSubmit={(e) => void f.handleSubmit(e)}>
      <div className="spool-add-grid">
        <TextField
          id="spool-material"
          label="Material *"
          placeholder="e.g. PLA, PETG"
          value={f.material}
          onChange={f.setMaterial}
          disabled={f.busy}
          required
        />

        <div className="field">
          <label htmlFor="spool-color">Colour</label>
          <div className="spool-color-row">
            <input
              id="spool-color"
              className="spool-color-input"
              type="color"
              value={f.color}
              onChange={(e) => f.setColor(e.target.value)}
              disabled={f.busy || !f.hasColor}
            />
            <label className="spool-color-none">
              <input
                type="checkbox"
                checked={!f.hasColor}
                onChange={(e) => f.setHasColor(!e.target.checked)}
                disabled={f.busy}
              />
              No colour
            </label>
          </div>
        </div>

        <TextField
          id="spool-name"
          label="Name"
          placeholder="optional"
          value={f.name}
          onChange={f.setName}
          disabled={f.busy}
        />
        <TextField
          id="spool-vendor"
          label="Vendor"
          placeholder="optional"
          value={f.vendor}
          onChange={f.setVendor}
          disabled={f.busy}
        />
        <TextField
          id="spool-grams"
          label="Initial grams"
          type="number"
          min={0}
          step={1}
          value={f.initialG}
          onChange={f.setInitialG}
          disabled={f.busy}
        />

        <div className="field">
          <label htmlFor="spool-module">Module</label>
          <select
            id="spool-module"
            className="map-select"
            value={f.moduleId}
            onChange={(e) => f.setModuleId(e.target.value)}
            disabled={f.busy}
          >
            <option value="">— unassigned —</option>
            {f.modules.map((m) => (
              <option key={m.id} value={m.id}>
                {m.id}
              </option>
            ))}
          </select>
        </div>
      </div>

      {f.error && <div className="error">{f.error}</div>}

      <div className="spool-add-actions">
        <button className="btn btn-primary" type="submit" disabled={f.busy}>
          {f.busy ? "Adding…" : "Add spool"}
        </button>
        <button className="btn" type="button" onClick={onCancel} disabled={f.busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}
