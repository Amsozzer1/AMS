"use client";

import { useEffect, useRef, useState } from "react";
import {
  listPrinters,
  submitJob,
  type JobResult,
  type PrinterState,
} from "@/lib/api";

// Pick a printer + a sliced .gcode.3mf (drag/drop or browse), POST it, and
// render the returned ordered swap plan. "Arm only" calls ?start=false so the
// plan is staged but the operator starts the print themselves (Bambu Studio).
// A bad/sliceless file surfaces the server's 400 detail message.
export default function JobUpload() {
  const [printers, setPrinters] = useState<PrinterState[]>([]);
  const [printerId, setPrinterId] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [armOnly, setArmOnly] = useState(false);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Populate the printer picker once on mount (cards handle live polling).
  useEffect(() => {
    const controller = new AbortController();
    listPrinters(controller.signal)
      .then((ps) => {
        setPrinters(ps);
        setPrinterId((cur) => cur || ps[0]?.id || "");
      })
      .catch(() => {
        /* picker stays empty; dashboard shows the connection error */
      });
    return () => controller.abort();
  }, []);

  // The Brain only parses a sliced .gcode.3mf. Browsers key `accept` off a single trailing
  // extension and ignore the double ".gcode.3mf" (showing all files), so we filter the browse
  // dialog on ".3mf" and enforce the full ".gcode.3mf" here — which also covers drag-drop.
  function isSliced3mf(f: File) {
    return f.name.toLowerCase().endsWith(".gcode.3mf");
  }

  function pickFile(f: File | null | undefined) {
    if (!f) return;
    setResult(null);
    if (!isSliced3mf(f)) {
      setFile(null);
      setError(`${f.name} isn't a sliced .gcode.3mf — that's the only format the Brain parses.`);
      return;
    }
    setError(null);
    setFile(f);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setOver(false);
    pickFile(e.dataTransfer.files?.[0]);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!printerId || !file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await submitJob(printerId, file, !armOnly);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="section-head">
        <h2>Job intake</h2>
        <span className="count">.gcode.3mf</span>
      </div>

      <form className="intake" onSubmit={onSubmit}>
        <div className="intake-controls">
          <div className="field">
            <label htmlFor="printer-select">Printer</label>
            <select
              id="printer-select"
              className="select"
              value={printerId}
              onChange={(e) => setPrinterId(e.target.value)}
            >
              {printers.length === 0 && <option value="">no printers</option>}
              {printers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.id}
                </option>
              ))}
            </select>
          </div>

          <div
            className={`dropzone${over ? " over" : ""}${file ? " has-file" : ""}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={onDrop}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                inputRef.current?.click();
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
              accept=".gcode.3mf,.3mf,model/3mf,application/vnd.ms-package.3dmanufacturing-3dmodelplus+xml"
              hidden
              onChange={(e) => pickFile(e.target.files?.[0])}
            />
          </div>
        </div>

        <div className="intake-actions">
          <button
            className="btn btn-primary"
            type="submit"
            disabled={busy || !printerId || !file}
          >
            {busy ? "Planning…" : armOnly ? "Arm plan" : "Plan & start print"}
          </button>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={armOnly}
              onChange={(e) => setArmOnly(e.target.checked)}
            />
            Arm only — I&apos;ll start the print
          </label>
        </div>

        {error && <div className="error">{error}</div>}

        {result && (
          <div className="swap-plan">
            <div className="plan-head">
              <span>
                {result.filename} — <span className="ok-tag">{armOnly ? "armed" : "started"}</span>
              </span>
              <span>
                {result.planned_swaps.length} swap
                {result.planned_swaps.length === 1 ? "" : "s"}
              </span>
            </div>
            {result.planned_swaps.length === 0 ? (
              <div className="empty">No material changes found in this job.</div>
            ) : (
              <div className="plan-list">
                {result.planned_swaps.map((s) => (
                  <div className="plan-step" key={s.seq}>
                    <span className="step-seq">{s.seq}</span>
                    <span className="arrow">→</span>
                    <span className="step-fil">filament {s.filament_index}</span>
                    <span className="step-tag">{s.tag}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </form>
    </section>
  );
}
