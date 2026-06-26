"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSpool,
  deleteSpool,
  listModules,
  listSpools,
  updateSpool,
  type ModuleInfo,
  type Spool,
} from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

// =============================================================================
// Spool inventory manager — a compact list of every spool the Brain knows about
// (Spoolman or the fake store) with inline CRUD actions.
//
// One line per spool: a real colour swatch, name + material, remaining grams,
// the module it's loaded in (if any), and per-row actions (edit grams, archive,
// delete). An "Add spool" disclosure form lets the operator register a new spool.
//
// Soft by design: Spoolman may be down or unconfigured, so an error or an empty
// list shows a calm empty state — the rest of the dashboard keeps working.
// Write errors (create / update / delete) are shown inline and never blank the
// existing list.
// =============================================================================

const POLL_MS = 5000;

function swatchColor(hex: string | null): string {
  if (hex && /^[0-9a-fA-F]{6}$/.test(hex)) return `#${hex}`;
  return "#9b948333";
}

function gramsLabel(g: number | null): string {
  if (typeof g !== "number") return "—";
  return `${Math.round(g)} g`;
}

// ---- Per-row actions -------------------------------------------------------

interface SpoolRowProps {
  s: Spool;
  onRefresh: () => void;
}

function SpoolRow({ s, onRefresh }: SpoolRowProps) {
  const title = s.name || s.material || s.filament_id || s.id;

  // Edit remaining grams
  const [editing, setEditing] = useState(false);
  const [gramsDraft, setGramsDraft] = useState<string>("");
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const startEdit = useCallback(() => {
    setGramsDraft(typeof s.remaining_g === "number" ? String(Math.round(s.remaining_g)) : "");
    setEditError(null);
    setEditing(true);
  }, [s.remaining_g]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const submitEdit = useCallback(async () => {
    const val = parseFloat(gramsDraft);
    if (isNaN(val) || val < 0) {
      setEditError("Enter a valid non-negative number.");
      return;
    }
    // Clear all row errors so only this action's error can show.
    setEditError(null);
    setArchiveError(null);
    setDeleteError(null);
    setEditBusy(true);
    try {
      await updateSpool(s.id, { remaining_g: val });
      setEditing(false);
      onRefresh();
    } catch (err) {
      setEditError(err instanceof Error ? err.message : String(err));
    } finally {
      setEditBusy(false);
    }
  }, [s.id, gramsDraft, onRefresh]);

  const cancelEdit = useCallback(() => {
    setEditing(false);
    setEditError(null);
  }, []);

  // Archive
  const [archiveBusy, setArchiveBusy] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  const doArchive = useCallback(async () => {
    // Clear all row errors so only this action's error can show.
    setEditError(null);
    setArchiveError(null);
    setDeleteError(null);
    setArchiveBusy(true);
    try {
      await updateSpool(s.id, { archived: true });
      onRefresh();
    } catch (err) {
      setArchiveError(err instanceof Error ? err.message : String(err));
    } finally {
      setArchiveBusy(false);
    }
  }, [s.id, onRefresh]);

  // Delete
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const doDelete = useCallback(async () => {
    if (!window.confirm(`Delete spool "${title}"? This cannot be undone.`)) return;
    // Clear all row errors so only this action's error can show.
    setEditError(null);
    setArchiveError(null);
    setDeleteError(null);
    setDeleteBusy(true);
    try {
      await deleteSpool(s.id);
      onRefresh();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeleteBusy(false);
    }
  }, [s.id, title, onRefresh]);

  const rowError = editError || archiveError || deleteError;

  return (
    <div className="spool-item spool-item--managed">
      {/* identity row */}
      <span
        className="swatch-lg swatch"
        style={{ background: swatchColor(s.color_hex), marginRight: 0, flexShrink: 0 }}
        aria-hidden
      />
      <span className="meta">
        <span className="name">{title}</span>
        <span className="sub">{s.material || "—"}</span>
      </span>

      {/* grams — inline edit or read-only */}
      {editing ? (
        <span className="spool-grams-edit">
          <input
            ref={inputRef}
            className="spool-grams-input"
            type="number"
            min={0}
            step={1}
            value={gramsDraft}
            onChange={(e) => setGramsDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void submitEdit();
              if (e.key === "Escape") cancelEdit();
            }}
            aria-label="Remaining grams"
            disabled={editBusy}
          />
          <button
            className="btn spool-act-btn"
            type="button"
            onClick={() => void submitEdit()}
            disabled={editBusy}
          >
            {editBusy ? "…" : "Save"}
          </button>
          <button
            className="btn spool-act-btn"
            type="button"
            onClick={cancelEdit}
            disabled={editBusy}
          >
            Cancel
          </button>
        </span>
      ) : (
        <span className="grams">{gramsLabel(s.remaining_g)}</span>
      )}

      <span className={`mod-chip${s.module ? "" : " empty"}`}>
        {s.module || "unloaded"}
      </span>

      {/* per-row actions */}
      {!editing && (
        <span className="spool-actions">
          <button
            className="btn spool-act-btn"
            type="button"
            onClick={startEdit}
            title="Edit remaining grams"
          >
            Edit g
          </button>
          <button
            className="btn spool-act-btn"
            type="button"
            onClick={() => void doArchive()}
            disabled={archiveBusy}
            title="Archive this spool"
          >
            {archiveBusy ? "…" : "Archive"}
          </button>
          <button
            className="btn spool-act-btn spool-act-btn--danger"
            type="button"
            onClick={() => void doDelete()}
            disabled={deleteBusy}
            title="Delete this spool"
          >
            {deleteBusy ? "…" : "Delete"}
          </button>
        </span>
      )}

      {rowError && (
        <span className="spool-row-error error">{rowError}</span>
      )}
    </div>
  );
}

// ---- Add-spool form --------------------------------------------------------

interface AddSpoolFormProps {
  onSuccess: () => void;
  onCancel: () => void;
}

function AddSpoolForm({ onSuccess, onCancel }: AddSpoolFormProps) {
  const [material, setMaterial] = useState("");
  const [color, setColor] = useState("#ffffff");
  const [name, setName] = useState("");
  const [vendor, setVendor] = useState("");
  const [initialG, setInitialG] = useState("1000");
  const [moduleId, setModuleId] = useState("");
  const [modules, setModules] = useState<ModuleInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load module list once on mount
  useEffect(() => {
    const controller = new AbortController();
    listModules(controller.signal)
      .then(setModules)
      .catch(() => {
        // Non-fatal: the form works without a module selection
      });
    return () => controller.abort();
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!material.trim()) {
        setError("Material is required.");
        return;
      }
      const grams = parseFloat(initialG);
      if (isNaN(grams) || grams < 0) {
        setError("Initial grams must be a non-negative number.");
        return;
      }
      // Strip the '#' from the colour picker value before sending
      const bareHex = color.replace(/^#/, "");
      setBusy(true);
      setError(null);
      try {
        await createSpool({
          material: material.trim(),
          color_hex: bareHex,
          name: name.trim() || undefined,
          vendor: vendor.trim() || undefined,
          initial_g: grams,
          module: moduleId || undefined,
        });
        onSuccess();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [material, color, name, vendor, initialG, moduleId, onSuccess],
  );

  return (
    <form className="spool-add-form" onSubmit={(e) => void handleSubmit(e)}>
      <div className="spool-add-grid">
        {/* material — required */}
        <div className="field">
          <label htmlFor="spool-material">Material *</label>
          <input
            id="spool-material"
            className="spool-text-input"
            type="text"
            placeholder="e.g. PLA, PETG"
            value={material}
            onChange={(e) => setMaterial(e.target.value)}
            required
            disabled={busy}
          />
        </div>

        {/* colour picker */}
        <div className="field">
          <label htmlFor="spool-color">Colour</label>
          <input
            id="spool-color"
            className="spool-color-input"
            type="color"
            value={color}
            onChange={(e) => setColor(e.target.value)}
            disabled={busy}
          />
        </div>

        {/* optional name */}
        <div className="field">
          <label htmlFor="spool-name">Name</label>
          <input
            id="spool-name"
            className="spool-text-input"
            type="text"
            placeholder="optional"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy}
          />
        </div>

        {/* optional vendor */}
        <div className="field">
          <label htmlFor="spool-vendor">Vendor</label>
          <input
            id="spool-vendor"
            className="spool-text-input"
            type="text"
            placeholder="optional"
            value={vendor}
            onChange={(e) => setVendor(e.target.value)}
            disabled={busy}
          />
        </div>

        {/* initial grams */}
        <div className="field">
          <label htmlFor="spool-grams">Initial grams</label>
          <input
            id="spool-grams"
            className="spool-text-input"
            type="number"
            min={0}
            step={1}
            value={initialG}
            onChange={(e) => setInitialG(e.target.value)}
            disabled={busy}
          />
        </div>

        {/* module select */}
        <div className="field">
          <label htmlFor="spool-module">Module</label>
          <select
            id="spool-module"
            className="map-select"
            value={moduleId}
            onChange={(e) => setModuleId(e.target.value)}
            disabled={busy}
          >
            <option value="">— unassigned —</option>
            {modules.map((m) => (
              <option key={m.id} value={m.id}>
                {m.id}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="spool-add-actions">
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? "Adding…" : "Add spool"}
        </button>
        <button
          className="btn"
          type="button"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

// ---- Main panel ------------------------------------------------------------

export default function SpoolInventory() {
  const { data, error, loading, refresh } = usePolling(listSpools, POLL_MS);
  const spools = (data ?? []).filter((s) => !s.archived);

  const [showAdd, setShowAdd] = useState(false);

  const handleAddSuccess = useCallback(() => {
    setShowAdd(false);
    refresh();
  }, [refresh]);

  const handleAddCancel = useCallback(() => {
    setShowAdd(false);
  }, []);

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Spool inventory</h3>
        <div className="panel-head-actions">
          {spools.length > 0 && <span className="count">{spools.length}</span>}
          <button
            className="btn spool-add-toggle"
            type="button"
            onClick={() => setShowAdd((v) => !v)}
            aria-expanded={showAdd}
          >
            {showAdd ? "Cancel" : "+ Add spool"}
          </button>
        </div>
      </div>

      {showAdd && (
        <AddSpoolForm onSuccess={handleAddSuccess} onCancel={handleAddCancel} />
      )}

      {loading && spools.length === 0 && !error ? (
        <p className="mapping-sub">Loading inventory…</p>
      ) : error ? (
        <div className="empty">
          Inventory unavailable — Spoolman may be down or unconfigured.
        </div>
      ) : spools.length === 0 ? (
        <div className="empty">No spools in inventory.</div>
      ) : (
        <div className="spool-list">
          {spools.map((s) => (
            <SpoolRow key={s.id} s={s} onRefresh={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}
