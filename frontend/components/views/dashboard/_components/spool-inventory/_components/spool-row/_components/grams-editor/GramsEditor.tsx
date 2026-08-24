"use client";

import type { RefObject } from "react";

/** Inline remaining-grams editor. Enter saves, Escape cancels. */
export default function GramsEditor({
  value,
  onChange,
  onSave,
  onCancel,
  busy,
  inputRef,
}: {
  value: string;
  onChange: (v: string) => void;
  onSave: () => void;
  onCancel: () => void;
  busy: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
}) {
  return (
    <span className="spool-grams-edit">
      <input
        ref={inputRef}
        className="spool-grams-input"
        type="number"
        min={0}
        step={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onSave();
          if (e.key === "Escape") onCancel();
        }}
        aria-label="Remaining grams"
        disabled={busy}
      />
      <button className="btn spool-act-btn" type="button" onClick={onSave} disabled={busy}>
        {busy ? "…" : "Save"}
      </button>
      <button className="btn spool-act-btn" type="button" onClick={onCancel} disabled={busy}>
        Cancel
      </button>
    </span>
  );
}
