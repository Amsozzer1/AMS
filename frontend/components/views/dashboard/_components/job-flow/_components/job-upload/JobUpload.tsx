"use client";

// Step one of the two-step job flow: pick a printer + a sliced .gcode.3mf and ARM it
// (?start=false). Arming stages the plan and computes the colour→module proposal WITHOUT
// starting the print — the operator maps colours and confirms in the mapping panel.

import { useEffect, useState } from "react";
import { API, type PrinterState } from "@/api";
import { isSliced3mf } from "./_helpers";
import Dropzone from "./_components/dropzone";

export default function JobUpload({ onArmed }: { onArmed: (printerId: string) => void }) {
  const [printers, setPrinters] = useState<PrinterState[]>([]);
  const [printerId, setPrinterId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Populate the picker once on mount — the cards handle live polling.
  useEffect(() => {
    const controller = new AbortController();
    API.printers
      .list({ signal: controller.signal })
      .then((ps) => {
        setPrinters(ps);
        setPrinterId((cur) => cur || ps[0]?.id || "");
      })
      .catch(() => {
        /* picker stays empty; the dashboard surfaces the connection error */
      });
    return () => controller.abort();
  }, []);

  function pickFile(f: File | null | undefined) {
    if (!f) return;
    if (!isSliced3mf(f)) {
      setFile(null);
      setError(`${f.name} isn't a sliced .gcode.3mf — that's the only format the Brain parses.`);
      return;
    }
    setError(null);
    setFile(f);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!printerId || !file) return;
    setBusy(true);
    setError(null);
    try {
      // Arm only — never auto-start. The operator confirms the mapping to start.
      await API.jobs.submit(printerId, file, false);
      onArmed(printerId);
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

          <Dropzone file={file} onPick={pickFile} />
        </div>

        <div className="intake-actions">
          <button className="btn btn-primary" type="submit" disabled={busy || !printerId || !file}>
            {busy ? "Arming…" : "Upload & Arm"}
          </button>
          <span className="checkbox" style={{ cursor: "default" }}>
            Arms the plan — map colours below, then Confirm &amp; Start.
          </span>
        </div>

        {error && <div className="error">{error}</div>}
      </form>
    </section>
  );
}
