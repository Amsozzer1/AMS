import type { JsonValue } from "@/types";

/** `raw.print` — the printer's own status blob. Shape is printer- and firmware-dependent and
 *  may be sparse (simulate mode reports almost nothing), so every read goes through the
 *  defensive coercers in `printer-detail.functions.ts`. */
export type PrintReport = { [key: string]: JsonValue };
