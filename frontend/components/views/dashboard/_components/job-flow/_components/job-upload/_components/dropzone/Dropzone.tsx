"use client";

import { useRef, useState } from "react";
import { FILE_ACCEPT } from "../../_helpers";

/** Drag-drop / click-to-browse target for the sliced 3MF. Validation lives with the caller —
 *  this only reports what the operator picked. */
export default function Dropzone({
  file,
  onPick,
}: {
  file: File | null;
  onPick: (f: File | null | undefined) => void;
}) {
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const open = () => inputRef.current?.click();

  return (
    <div
      className={`dropzone${over ? " over" : ""}${file ? " has-file" : ""}`}
      onClick={open}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        onPick(e.dataTransfer.files?.[0]);
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      }}
      aria-label="Drop a .gcode.3mf file or browse"
    >
      <span className="dz-icon" aria-hidden>
        {file ? "▣" : "⤓"}
      </span>
      <span className="dz-text">
        {file ? (
          <>
            <strong>{file.name}</strong>
            <span>{(file.size / 1024).toFixed(0)} KB · click to replace</span>
          </>
        ) : (
          <>
            <strong>Drop a sliced .gcode.3mf</strong>
            <span>or click to browse</span>
          </>
        )}
      </span>
      <input
        ref={inputRef}
        type="file"
        accept={FILE_ACCEPT}
        hidden
        onChange={(e) => onPick(e.target.files?.[0])}
      />
    </div>
  );
}
