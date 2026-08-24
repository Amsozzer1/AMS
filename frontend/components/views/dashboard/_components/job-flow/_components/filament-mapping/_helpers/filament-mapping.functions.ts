import type { AssignRow } from "@/api";

/** Which module the operator has effectively chosen for a row: their pick, else the
 *  resolver's proposal, else nothing. */
export function pickedModule(r: AssignRow, choice: Record<number, string>): string {
  return choice[r.index] ?? r.module ?? "";
}

/** A row is a gap only while the resolver flagged it AND the operator has not picked a
 *  module. Once a module is chosen it reads as resolvable, even if the store disagrees. */
export function isGap(r: AssignRow, choice: Record<number, string>): boolean {
  return r.status === "gap" && !choice[r.index];
}

export function countGaps(rows: AssignRow[], choice: Record<number, string>): number {
  return rows.filter((r) => isGap(r, choice)).length;
}

/** Seed local choices from the proposal so untouched rows confirm exactly as proposed. */
export function seedChoices(rows: AssignRow[]): Record<number, string> {
  const seed: Record<number, string> = {};
  for (const r of rows) if (r.module) seed[r.index] = r.module;
  return seed;
}

/** The index→module body the server expects. Rows with no module are omitted. */
export function buildMapping(
  rows: AssignRow[],
  choice: Record<number, string>,
): Record<number, string> {
  const mapping: Record<number, string> = {};
  for (const r of rows) {
    const m = pickedModule(r, choice);
    if (m) mapping[r.index] = m;
  }
  return mapping;
}
