"use client";

import { useCallback } from "react";
import { API } from "@/api";
import { POLL_MS } from "@/constants";
import { usePolling } from "@/hooks";
import { humanSwapNumber, isHeld, isPassed } from "../../_helpers";
import StatePill from "../state-pill";

/** One printer's swap loop. Renders nothing until a plan is armed. */
export default function OrchStrip({ printerId }: { printerId: string }) {
  const fetcher = useCallback(
    (signal: AbortSignal) => API.printers.orchestrator(printerId, { signal }),
    [printerId],
  );
  const { data } = usePolling(fetcher, POLL_MS.ORCHESTRATOR);

  if (!data || data.armed !== true) return null;
  const s = data;
  const held = isHeld(s);

  return (
    <div className={`swap-strip${held ? " held" : ""}`} style={{ marginBottom: "var(--s-4)" }}>
      <div className="swap-strip-head">
        <div>
          <div className="swap-counter">
            <span className="mono">{printerId}</span> · Swap {humanSwapNumber(s)}{" "}
            <span className="of">of {s.total}</span>
          </div>
        </div>
        <StatePill s={s} />
      </div>

      <div className="swap-track">
        {s.swaps.map((sw) => {
          const cls = sw.current ? "current" : isPassed(s, sw.seq, sw.current) ? "passed" : "";
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
