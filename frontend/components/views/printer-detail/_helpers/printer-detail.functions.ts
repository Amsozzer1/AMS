import type { PrinterDetail } from "@/api";
import type { JsonValue } from "@/types";
import type { PrintReport } from "./printer-detail.types";

/** Pull `raw.print` out of the open-JSON report.
 *
 *  `raw` carries `unknown` values because the report is firmware-dependent. The guard is the
 *  runtime proof that this one is a plain object; the cast only tells the type system what
 *  the guard already established. */
export function printReport(d: PrinterDetail): PrintReport {
  const p = d.raw?.print;
  return p && typeof p === "object" && !Array.isArray(p) ? (p as PrintReport) : {};
}

export function num(v: JsonValue | undefined): number | null {
  return typeof v === "number" ? v : null;
}

export function str(v: JsonValue | undefined): string | null {
  if (typeof v === "string") return v;
  if (typeof v === "number") return String(v);
  return null;
}

/** `"210°C → 220°C"`, or just the current reading when there is no target. */
export function temp(cur: JsonValue | undefined, target: JsonValue | undefined): string {
  const c = num(cur);
  const t = num(target);
  if (c === null) return "—";
  const cTxt = `${Math.round(c)}°C`;
  return t && t > 0 ? `${cTxt} → ${Math.round(t)}°C` : cTxt;
}

/** Minutes as `"2h 15m"` / `"15m"`, or an em dash when there is no estimate. */
export function minutes(v: JsonValue | undefined): string {
  const m = num(v);
  if (m === null || m <= 0) return "—";
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return h > 0 ? `${h}h ${mm}m` : `${mm}m`;
}

/** hms entries are health/error codes. Shape varies by firmware, so they render generically
 *  — but they surface first, above everything else, when present. */
export function hmsMessages(report: PrintReport): JsonValue[] {
  const hms = report.hms;
  return Array.isArray(hms) ? hms : [];
}
