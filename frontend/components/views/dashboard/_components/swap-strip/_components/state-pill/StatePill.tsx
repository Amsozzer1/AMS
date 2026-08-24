import type { OrchestratorArmed } from "@/api";

/** The swap loop's live state as one chip. Fault and held both read as "fault" styling —
 *  an operator must not have to tell them apart at a glance. */
export default function StatePill({ s }: { s: OrchestratorArmed }) {
  const cls = s.held || s.swap_state === "FAULT" ? "fault" : s.done ? "done" : "";
  const label = s.done ? "complete" : s.held ? "held" : s.swap_state.toLowerCase();
  return <span className={`swap-state-chip ${cls}`}>{label}</span>;
}
