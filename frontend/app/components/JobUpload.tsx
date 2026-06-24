"use client";

import { useEffect, useState } from "react";
import {
  listPrinters,
  submitJob,
  type JobResult,
  type PrinterState,
} from "@/lib/api";

// Pick a printer + a sliced .gcode.3mf, POST it, and render the returned swap
// plan. A bad/sliceless file surfaces the server's 400 detail message.
export default function JobUpload() {
  const [printers, setPrinters] = useState<PrinterState[]>([]);
  const [printerId, setPrinterId] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);

  // Populate the printer picker once on mount (the cards section handles live polling).
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

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!printerId || !file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await submitJob(printerId, file);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2>Submit a job (.gcode.3mf)</h2>
      <form className="upload-form" onSubmit={onSubmit}>
        <select
          value={printerId}
          onChange={(e) => setPrinterId(e.target.value)}
          aria-label="printer"
        >
          {printers.length === 0 && <option value="">no printers</option>}
          {printers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.id}
            </option>
          ))}
        </select>
        <input
          type="file"
          accept=".3mf,.gcode.3mf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          aria-label="3mf file"
        />
        <button
          className="btn"
          type="submit"
          disabled={busy || !printerId || !file}
        >
          {busy ? "Uploading…" : "Upload & plan"}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {result && (
        <div className="swap-plan">
          <div className="row">
            <span className="k">file</span>
            <span>{result.filename}</span>
          </div>
          {result.planned_swaps.length === 0 ? (
            <div className="prompt-empty">
              No material changes found in this job.
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>seq</th>
                  <th>filament index</th>
                  <th>tag</th>
                </tr>
              </thead>
              <tbody>
                {result.planned_swaps.map((s) => (
                  <tr key={s.seq}>
                    <td>{s.seq}</td>
                    <td>{s.filament_index}</td>
                    <td>{s.tag}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}
