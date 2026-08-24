/** Poll intervals, in milliseconds — one place, named per surface.
 *
 *  These were six separate `POLL_MS` constants across six components with five different
 *  values and no way to see them together. Cadence is a product decision: the prompt panel is
 *  the hero and must feel instant; inventory can lag. */
export const POLL_MS = {
  /** Human-swap prompts — the hero surface. Must feel immediate. */
  PROMPTS: 1000,
  /** Printer cards on the dashboard. */
  PRINTERS: 1000,
  /** Live swap-loop state for an armed printer. */
  ORCHESTRATOR: 1000,
  /** Single-printer detail drill-in. */
  PRINTER_DETAIL: 1500,
  /** Printer list backing the swap strip — slower, it only supplies ids. */
  SWAP_STRIP_PRINTERS: 4000,
  /** Brain health pill. */
  HEALTH: 5000,
  /** Spool inventory and per-printer loadout. */
  INVENTORY: 5000,
} as const;
