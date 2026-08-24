import type { JsonValue } from "@/types";

/** Narrow to the values that get a collapsible node rather than an inline scalar. */
export function isContainer(v: JsonValue): v is JsonValue[] | { [k: string]: JsonValue } {
  return v !== null && typeof v === "object";
}

/** The collapsed-state label for a container: `[ 3 ]` for arrays, `{ 7 }` for objects. */
export function summarize(v: JsonValue): string {
  if (Array.isArray(v)) return `[ ${v.length} ]`;
  return `{ ${Object.keys(v as object).length} }`;
}
