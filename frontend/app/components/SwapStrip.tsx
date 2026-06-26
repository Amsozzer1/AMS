"use client";

import { useCallback } from "react";
import {
  getOrchestrator,
  listPrinters,
  type OrchestratorArmed,
} from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

// Live swap-loop status. For each printer we poll GET /…/orchestrator; before a
// job is armed it returns `{ armed:false }` and we render nothing for it. When
// armed we show "Swap N of M", the sequence of swap pips with the current one
// highlighted, the live swap_state, and any held/alert state surfaced as a clear
// error (not decoration). Thin client: pure render of server state.

const PRINTERS_POLL_MS = 4000;
const ORCH_POLL_MS = 1000;

function StatePill({ s }: { s: OrchestratorArmed }) {
  const cls = s.held || s.swap_state === "FAULT" ? "fault" : s.done ? "done" : "";
  const label = s.done ? "complete" : s.held ? "held" : s.swap_state.toLowerCase();
  return <span className={`swap-state-chip ${cls}`}>{label}</span>;
}

function OrchStrip({ printerId }: { printerId: string }) {
  const fetcher = useCallback(
    (signal: AbortSignal) => getOrchestrator(printerId, signal),
    [printerId],
  );
  const { data } = usePolling(fetcher, ORCH_POLL_MS);

  // Render only when a plan is armed for this printer.
  if (!data || data.armed !== true) return null;
  const s = data;
  const held = s.held || s.swap_state === "FAULT" || s.alerts.length > 0;
  // cursor is 0-based into the plan; show a human 1-based "N of M".
  const human = Math.min(s.cursor + (s.done ? 0 : 1), s.total);

  return (
    <div
      className={`swap-strip${held ? " held" : ""}`}
      style={{ marginBottom: "var(--s-4)" }}
    >
      <div className="swap-strip-head">
        <div>
          <div className="swap-counter">
            <span className="mono">{printerId}</span> · Swap {s.done ? s.total : human}{" "}
            <span className="of">of {s.total}</span>
          </div>
        </div>
        <StatePill s={s} />
      </div>

      <div className="swap-track">
        {s.swaps.map((sw) => {
          const passed = !s.done && !sw.current && sw.seq < (s.swaps[s.cursor]?.seq ?? Infinity);
          const cls = sw.current ? "current" : s.done || passed ? "passed" : "";
          return (
            <div key={sw.seq} className={`swap-pip ${cls}`} title={sw.tag}>
              <span className="seq">{sw.seq}</span>
              <span>f{sw.filament_index}</span>
            </div>
          );
        })}
      </div>

      {held && (
        <div className="alert-list">
          {s.swap_state === "FAULT" && s.alerts.length === 0 && (
            <div className="alert-item">
              <span className="ai">!</span>
              Swap loop faulted. Check the printer and the module hardware.
            </div>
          )}
          {s.alerts.map((a, i) => (
            <div key={i} className="alert-item">
              <span className="ai">!</span>
              {a}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SwapStrip() {
  const { data } = usePolling(listPrinters, PRINTERS_POLL_MS);
  const printers = data ?? [];
  if (printers.length === 0) return null;

  return (
    <div style={{ marginBottom: "var(--s-6)" }}>
      {printers.map((p) => (
        <OrchStrip key={p.id} printerId={p.id} />
      ))}
    </div>
  );
}
