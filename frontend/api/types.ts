// The API layer's type surface.
//
// Server-derived shapes are RE-EXPORTS of `types.generated.ts`, which is produced from the
// Brain's OpenAPI schema (`npm run gen:api`). They are never hand-written here — that is the
// whole point: `server/src/amsx/api/models.py` is the single source of truth, so these types
// cannot drift from what the server actually sends.
//
// Only two things are hand-written below: `ApiError` (a runtime class, not a wire shape) and
// the UI-only aliases at the bottom, which describe how the UI *renders* server data rather
// than what the server returns.

import type { components } from "./types.generated";

type Schemas = components["schemas"];

// ---- requests ----
export type SpoolCreate = Schemas["SpoolCreate"];
export type SpoolUpdate = Schemas["SpoolUpdate"];

// ---- responses ----
export type Health = Schemas["Health"];
export type Progress = Schemas["Progress"];
export type LoadedFilament = Schemas["LoadedFilament"];
export type PrinterState = Schemas["PrinterState"];
export type PrinterDetail = Schemas["PrinterDetail"];

export type PlannedSwap = Schemas["PlannedSwap"];
export type JobResult = Schemas["JobResult"];
export type StartArmedResult = Schemas["StartArmedResult"];

export type Prompt = Schemas["Prompt"];
export type AnswerResult = Schemas["AnswerResult"];

export type OrchestratorSwap = Schemas["OrchestratorSwap"];
export type OrchestratorArmed = Schemas["OrchestratorArmed"];
export type OrchestratorIdle = Schemas["OrchestratorIdle"];
/** Discriminated on `armed` — narrow with `if (status.armed)` before reading swap fields. */
export type OrchestratorStatus = OrchestratorArmed | OrchestratorIdle;

export type ModuleInfo = Schemas["ModuleInfo"];
export type Spool = Schemas["Spool"];
export type LoadoutRow = Schemas["LoadoutRow"];
export type AssignRow = Schemas["AssignRow"];
export type AssignmentResponse = Schemas["AssignmentResponse"];

export type OkResponse = Schemas["OkResponse"];
export type DeleteResult = Schemas["DeleteResult"];
export type SimPauseResult = Schemas["SimPauseResult"];
export type SimSensorResult = Schemas["SimSensorResult"];

// ---- errors ----

/** A non-2xx response from the Brain.
 *
 *  `status` is the HTTP code and `detail` is FastAPI's `detail` field when present (falling
 *  back to the status line). Carrying the code lets callers tell the cases apart instead of
 *  showing one generic banner — 404 unknown printer, 409 nothing armed, 502 Spoolman down. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}
