// Typed client for the AMS-X Brain HTTP API.
//
// Shapes mirror server/src/amsx/api/__init__.py exactly — do not add fields the
// server does not return. This is a thin client: it only renders server state
// and relays operator actions. No business logic lives here.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://127.0.0.1:9001";

// ---- Response types (authoritative: api/__init__.py) ----

export interface LoadedFilament {
  index: number;
  material: string;
  color: string;
}

// Best-effort progress dict from the printer report (see server printer state:
// `{ layer?, percent?, line? }`). Any key may be absent; it's `{}` when idle.
export interface Progress {
  layer?: number;
  percent?: number;
  line?: number;
}

export interface PrinterState {
  id: string;
  stage: string;
  pause_reason: string | null;
  filament_sensor: boolean;
  progress: Progress;
  loaded_filament: LoadedFilament | null;
}

// Full printer detail from GET /api/printers/{id}/detail. Extends the basic
// PrinterState with connection metadata and the printer's complete own report
// under `raw`. `raw` is rendered generically (recursive tree) so nothing the
// Brain knows is hidden, so it stays an open-ended JSON value.
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface PrinterDetail extends PrinterState {
  serial: string;
  model: string;
  ip: string | null;
  simulate: boolean;
  connected: boolean;
  seeded: boolean;
  // The printer's full own report. `raw.print` carries the ~64 status fields
  // plus nested objects (ams, vt_tray, ipcam, net, ...). Shape is printer- and
  // firmware-dependent, so it's left as open JSON and rendered generically.
  raw: { print?: { [key: string]: JsonValue } } & { [key: string]: JsonValue };
}

export interface Health {
  ok: boolean;
  simulate: boolean;
  printers: string[];
  modules: number;
}

export interface PlannedSwap {
  seq: number;
  filament_index: number;
  tag: string;
}

export interface JobResult {
  printer_id: string;
  filename: string;
  planned_swaps: PlannedSwap[];
}

export interface Prompt {
  id: string;
  module_id: string;
  message: string;
}

export interface AnswerResult {
  ok: boolean;
  prompt_id: string;
}

// ---- Orchestrator (live swap loop) ----
// GET /api/printers/{id}/orchestrator returns either an armed status (below) or
// `{ armed: false, printer_id }` before a job is armed. The swap_state strings
// mirror the server state machine; treated as an opaque label by the UI.
export type SwapState =
  | "WATCHING"
  | "UNLOADING"
  | "SELECTING"
  | "FEEDING"
  | "SENSING"
  | "RESUMING"
  | "FAULT"
  | (string & {});

export interface OrchestratorSwap {
  seq: number;
  filament_index: number;
  tag: string;
  current: boolean;
}

export interface OrchestratorArmed {
  armed: true;
  printer_id: string;
  cursor: number;
  total: number;
  done: boolean;
  held: boolean;
  swap_state: SwapState;
  alerts: string[];
  swaps: OrchestratorSwap[];
}

export interface OrchestratorIdle {
  armed: false;
  printer_id: string;
}

export type OrchestratorStatus = OrchestratorArmed | OrchestratorIdle;

// ---- Fetch helpers ----

class ApiError extends Error {}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal, cache: "no-store" });
  if (!res.ok) {
    throw new ApiError(await extractError(res));
  }
  return (await res.json()) as T;
}

async function extractError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") return body.detail;
    return `${res.status} ${res.statusText}`;
  } catch {
    return `${res.status} ${res.statusText}`;
  }
}

// ---- Endpoints ----

export function getHealth(signal?: AbortSignal): Promise<Health> {
  return getJson<Health>("/health", signal);
}

export function listPrinters(signal?: AbortSignal): Promise<PrinterState[]> {
  return getJson<PrinterState[]>("/api/printers", signal);
}

export function getPrinter(id: string, signal?: AbortSignal): Promise<PrinterState> {
  return getJson<PrinterState>(`/api/printers/${encodeURIComponent(id)}`, signal);
}

/** Full detail for one printer, including the complete `raw` report. 404 if the
 *  printer id is unknown. */
export function getPrinterDetail(
  id: string,
  signal?: AbortSignal,
): Promise<PrinterDetail> {
  return getJson<PrinterDetail>(
    `/api/printers/${encodeURIComponent(id)}/detail`,
    signal,
  );
}

export function listPrompts(signal?: AbortSignal): Promise<Prompt[]> {
  return getJson<Prompt[]>("/api/prompts", signal);
}

/** Live swap-loop status for a printer. Returns `{ armed:false }` until a job is
 *  armed. The UI renders the swap progress strip from the armed shape. */
export function getOrchestrator(
  id: string,
  signal?: AbortSignal,
): Promise<OrchestratorStatus> {
  return getJson<OrchestratorStatus>(
    `/api/printers/${encodeURIComponent(id)}/orchestrator`,
    signal,
  );
}

/** Upload a sliced `.gcode.3mf` for a printer. When `start` is false the plan is
 *  ARMED only (the operator starts the print from Bambu Studio). Throws with the
 *  server's 400 detail message on a bad/sliceless file. */
export async function submitJob(
  printerId: string,
  file: File,
  start = true,
): Promise<JobResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(
    `${API_BASE}/api/printers/${encodeURIComponent(printerId)}/job?start=${start}`,
    { method: "POST", body: form, cache: "no-store" },
  );
  if (!res.ok) {
    throw new ApiError(await extractError(res));
  }
  return (await res.json()) as JobResult;
}

/** Resolve a pending human-swap prompt. `response` defaults to "done". */
export async function answerPrompt(
  promptId: string,
  response = "done",
): Promise<AnswerResult> {
  const res = await fetch(
    `${API_BASE}/api/prompts/${encodeURIComponent(promptId)}/answer?response=${encodeURIComponent(response)}`,
    { method: "POST", cache: "no-store" },
  );
  if (!res.ok) {
    throw new ApiError(await extractError(res));
  }
  return (await res.json()) as AnswerResult;
}
