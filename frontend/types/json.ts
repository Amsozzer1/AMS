/** Arbitrary JSON.
 *
 *  Used to render open-ended payloads (notably `PrinterDetail.raw`, whose shape is printer-
 *  and firmware-dependent) as a recursive tree. Deliberately NOT in `api/` — it describes how
 *  the UI walks unknown data, not anything the wire contract promises. */
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };
