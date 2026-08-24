import type { Prompt } from "@/api";

/** Split a server prompt into its module address and its instruction.
 *
 *  The message is free text like `"[module m2] START FEEDING…"` or
 *  `"Module m2 — START FEEDING filament 3"`. The module already renders as a big callout, so
 *  strip the leading prefix and keep only the instruction. Falls back to the raw message if
 *  the format differs, and to a generic instruction if it is empty. */
export function parseMessage(p: Prompt): { moduleId: string; instruction: string } {
  const moduleId = p.module_id || "—";
  let instruction = p.message?.trim() || "Feed the requested module, then confirm.";
  const stripped = instruction.replace(/^\[?\s*module\s+[^\]\s]+\s*\]?\s*[—\-:]?\s*/i, "").trim();
  if (stripped) instruction = stripped;
  return { moduleId, instruction };
}
