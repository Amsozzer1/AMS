"use client";

import type { Spool } from "@/api";
import { gramsLabel, swatchColor } from "@/utils";
import { useSpoolRowActions } from "./_helpers";
import GramsEditor from "./_components/grams-editor";

/** One spool: swatch, identity, remaining grams (inline-editable), its module, and the
 *  edit / archive / delete actions. Write errors show on the row and never blank the list. */
export default function SpoolRow({ s, onRefresh }: { s: Spool; onRefresh: () => void }) {
  const title = s.name || s.material || s.filament_id || s.id;
  const a = useSpoolRowActions(s, title, onRefresh);

  return (
    <div className="spool-item spool-item--managed">
      <span
        className="swatch-lg swatch"
        style={{ background: swatchColor(s.color_hex), marginRight: 0, flexShrink: 0 }}
        aria-hidden
      />
      <span className="meta">
        <span className="name">{title}</span>
        <span className="sub">{s.material || "—"}</span>
      </span>

      {a.editing ? (
        <GramsEditor
          value={a.gramsDraft}
          onChange={a.setGramsDraft}
          onSave={() => void a.submitEdit()}
          onCancel={a.cancelEdit}
          busy={a.editBusy}
          inputRef={a.inputRef}
        />
      ) : (
        <span className="grams">{gramsLabel(s.remaining_g)}</span>
      )}

      <span className={`mod-chip${s.module ? "" : " empty"}`}>{s.module || "unloaded"}</span>

      {!a.editing && (
        <span className="spool-actions">
          <button
            className="btn spool-act-btn"
            type="button"
            onClick={a.startEdit}
            title="Edit remaining grams"
          >
            Edit g
          </button>
          <button
            className="btn spool-act-btn"
            type="button"
            onClick={() => void a.doArchive()}
            disabled={a.archiveBusy}
            title="Archive this spool"
          >
            {a.archiveBusy ? "…" : "Archive"}
          </button>
          <button
            className="btn spool-act-btn spool-act-btn--danger"
            type="button"
            onClick={() => void a.doDelete()}
            disabled={a.deleteBusy}
            title="Delete this spool"
          >
            {a.deleteBusy ? "…" : "Delete"}
          </button>
        </span>
      )}

      {a.rowError && <span className="spool-row-error error">{a.rowError}</span>}
    </div>
  );
}
