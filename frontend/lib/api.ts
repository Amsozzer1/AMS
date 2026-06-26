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

// ---- Spool inventory + colour→module mapping (api/__init__.py spool endpoints) ----

// A spool of filament from the inventory (Spoolman or the fake store). `color_hex`
// is a bare 6-hex RRGGBB string (no leading `#`); any field may be null when the
// upstream record is sparse or Spoolman is unconfigured.
export interface Spool {
  id: string;
  filament_id: string;
  material: string | null;
  color_hex: string | null;
  name: string | null;
  remaining_g: number | null;
  module: string | null;
  archived: boolean;
}

// One configured module on a printer and the spool currently loaded into it
// (null when the module is empty). GET /api/printers/{id}/loadout returns one row
// per configured module.
export interface LoadoutRow {
  module: string;
  spool: Spool | null;
}

// One filament colour from the armed job's plan, with the module/spool the
// resolver proposed. `status` is "loaded" when a module is mapped (and the
// material/colour line up), or "gap" when the operator still needs to load this
// colour somewhere.
export interface AssignRow {
  index: number;
  material: string | null;
  color_hex: string | null;
  grams: number | null;
  module: string | null;
  spool_id: string | null;
  status: "loaded" | "gap";
}

// GET /api/printers/{id}/job/assignment. `rows` is empty when nothing is armed.
export interface AssignmentResponse {
  rows: AssignRow[];
  confirmed: boolean;
}

export interface StartArmedResult {
  printer_id: string;
  started: boolean;
}

// ---- Spool CRUD types (api/__init__.py SpoolCreate / SpoolUpdate) ----

/** Body for POST /api/spools. `color_hex` must be a bare 6-hex string (no `#`). */
export interface SpoolCreate {
  material: string;
  color_hex?: string;
  name?: string;
  vendor?: string;
  initial_g?: number;
  module?: string;
  location?: string;
}

/** Body for PATCH /api/spools/{id}. All fields optional. */
export interface SpoolUpdate {
  remaining_g?: number;
  location?: string;
  archived?: boolean;
}

/** One AMS module from GET /api/modules. `filament_index` is null when the
 *  module slot is unoccupied. */
export interface ModuleInfo {
  id: string;
  cluster_id: string;
  filament_index: number | null;
}

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

// ---- Spool inventory + loadout + assignment ----

/** All spools in the inventory. Returns `[]` (not an error) when the store is
 *  empty; throws only on transport/HTTP failure so callers can show a calm empty
 *  state when Spoolman is down or unconfigured. */
export function listSpools(signal?: AbortSignal): Promise<Spool[]> {
  return getJson<Spool[]>("/api/spools", signal);
}

/** Current spool→module loadout for a printer (one row per configured module). */
export function getLoadout(id: string, signal?: AbortSignal): Promise<LoadoutRow[]> {
  return getJson<LoadoutRow[]>(
    `/api/printers/${encodeURIComponent(id)}/loadout`,
    signal,
  );
}

/** Assign a spool to a module. Returns `{ ok: true }`. */
export async function setLoadout(
  printerId: string,
  module: string,
  spoolId: string,
): Promise<{ ok: boolean }> {
  const res = await fetch(
    `${API_BASE}/api/printers/${encodeURIComponent(printerId)}/loadout?module=${encodeURIComponent(module)}&spool_id=${encodeURIComponent(spoolId)}`,
    { method: "PUT", cache: "no-store" },
  );
  if (!res.ok) {
    throw new ApiError(await extractError(res));
  }
  return (await res.json()) as { ok: boolean };
}

/** The colour→module proposal for the armed job. `rows` is empty when nothing is
 *  armed; the UI shows the mapping panel only once rows arrive. */
export function getAssignment(
  printerId: string,
  signal?: AbortSignal,
): Promise<AssignmentResponse> {
  return getJson<AssignmentResponse>(
    `/api/printers/${encodeURIComponent(printerId)}/job/assignment`,
    signal,
  );
}

/** Confirm (and optionally override) the index→module mapping. The body is keyed
 *  by stringified filament index, as the server expects. Returns `{ ok: true }`. */
export async function confirmAssignment(
  printerId: string,
  mapping: Record<number, string>,
): Promise<{ ok: boolean }> {
  const body: Record<string, string> = {};
  for (const [index, moduleId] of Object.entries(mapping)) {
    body[String(index)] = moduleId;
  }
  const res = await fetch(
    `${API_BASE}/api/printers/${encodeURIComponent(printerId)}/job/assignment`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    },
  );
  if (!res.ok) {
    throw new ApiError(await extractError(res));
  }
  return (await res.json()) as { ok: boolean };
}

/** Push + start the job this printer is ALREADY armed with (does NOT re-arm, so
 *  the confirmed mapping is preserved). Throws with the server's 409 detail when
 *  nothing is armed, or 400 on a transport/start failure. */
export async function startArmedJob(
  printerId: string,
): Promise<StartArmedResult> {
  const res = await fetch(
    `${API_BASE}/api/printers/${encodeURIComponent(printerId)}/job/start`,
    { method: "POST", cache: "no-store" },
  );
  if (!res.ok) {
    throw new ApiError(await extractError(res));
  }
  return (await res.json()) as StartArmedResult;
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

// ---- Spool CRUD ----

/** All configured AMS modules. Used to populate the module dropdown in the
 *  add-spool form. Returns `[]` when no modules are configured. */
export function listModules(signal?: AbortSignal): Promise<ModuleInfo[]> {
  return getJson<ModuleInfo[]>("/api/modules", signal);
}

/** Create a new spool in the inventory. `body.color_hex` must be bare 6-hex
 *  (no leading `#`). Throws `ApiError` with the server's `detail` on 422/502. */
export async function createSpool(body: SpoolCreate): Promise<Spool> {
  const res = await fetch(`${API_BASE}/api/spools`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new ApiError(await extractError(res));
  }
  return (await res.json()) as Spool;
}

/** Update mutable fields on an existing spool. Throws `ApiError` with the
 *  server's `detail` on 404/502. */
export async function updateSpool(id: string, body: SpoolUpdate): Promise<Spool> {
  const res = await fetch(`${API_BASE}/api/spools/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new ApiError(await extractError(res));
  }
  return (await res.json()) as Spool;
}

/** Delete a spool by id. Returns `{ ok: true, id }`. Throws `ApiError` with the
 *  server's `detail` on 404/502. */
export async function deleteSpool(id: string): Promise<{ ok: boolean; id: string }> {
  const res = await fetch(`${API_BASE}/api/spools/${encodeURIComponent(id)}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (!res.ok) {
    throw new ApiError(await extractError(res));
  }
  return (await res.json()) as { ok: boolean; id: string };
}
