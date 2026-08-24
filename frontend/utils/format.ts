/** Display helpers for server values that may be null. All render an em dash for "unknown"
 *  rather than 0 or an empty string — a missing reading must never look like a real one. */

/** Grams as a rounded label: `1000` -> `"1000 g"`, null -> `"—"`. */
export function gramsLabel(g: number | null | undefined): string {
  if (typeof g !== "number") return "—";
  return `${Math.round(g)} g`;
}

/** Clamp a percentage to a whole 0–100, or null when there is no reading. */
export function clampPct(v: number | null | undefined): number | null {
  if (typeof v !== "number" || Number.isNaN(v)) return null;
  return Math.max(0, Math.min(100, Math.round(v)));
}
