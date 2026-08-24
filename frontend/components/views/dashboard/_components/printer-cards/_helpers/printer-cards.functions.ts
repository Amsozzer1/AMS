/** Map the free-text stage string onto a signal colour class.
 *
 *  The server's stage vocabulary is open (it mirrors whatever the printer reports), so this
 *  matches on substrings and falls back to neutral rather than switching on an enum that
 *  firmware could extend underneath us. */
export function stageClass(stage: string, paused: boolean): string {
  const s = stage.toLowerCase();
  if (paused || s.includes("pause") || s.includes("swap")) return "stage-act";
  if (s.includes("error") || s.includes("fault") || s.includes("fail")) return "stage-fault";
  if (s.includes("run") || s.includes("print") || s.includes("working")) return "stage-run";
  return "stage-idle";
}
