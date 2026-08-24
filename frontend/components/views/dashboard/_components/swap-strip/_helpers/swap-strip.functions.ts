import type { OrchestratorArmed } from "@/api";

/** True when the loop needs an operator's eyes: explicitly held, faulted, or carrying alerts. */
export function isHeld(s: OrchestratorArmed): boolean {
  return s.held || s.swap_state === "FAULT" || s.alerts.length > 0;
}

/** `cursor` is 0-based into the plan; operators count from 1. Clamps at the total so a
 *  finished plan reads "N of N" rather than overshooting. */
export function humanSwapNumber(s: OrchestratorArmed): number {
  if (s.done) return s.total;
  return Math.min(s.cursor + 1, s.total);
}

/** Whether a pip is behind the cursor — used to render it as already passed. */
export function isPassed(s: OrchestratorArmed, seq: number, current: boolean): boolean {
  if (s.done) return true;
  if (current) return false;
  return seq < (s.swaps[s.cursor]?.seq ?? Infinity);
}
