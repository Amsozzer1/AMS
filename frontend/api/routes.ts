// The API surface, as one config object.
//
// This is the ONLY file in the app that knows a URL or an HTTP verb. Callers say
// `API.spools.create(body)` — they never learn the path, the method, or that HTTP is involved
// (CLAUDE.md RULE 1). Adding an endpoint is one line here; nothing else in the app changes.
//
// Grouping mirrors the Brain's own domains, so `API.` in an editor lists the whole backend.
// Every read takes an optional `RequestConfig` last, which is how `usePolling` threads its
// AbortSignal through so unmounts cancel in-flight requests.

import { request } from "./request";
import type { RequestConfig } from "./client";
import type {
  AnswerResult,
  AssignmentResponse,
  DeleteResult,
  Health,
  JobResult,
  LoadoutRow,
  ModuleInfo,
  OkResponse,
  OrchestratorStatus,
  PrinterDetail,
  PrinterState,
  Prompt,
  SimPauseResult,
  SimSensorResult,
  Spool,
  SpoolCreate,
  SpoolUpdate,
  StartArmedResult,
} from "./types";

const enc = encodeURIComponent;

export const API = {
  /** Liveness + how the Brain is configured (simulate mode, printer ids, module count). */
  health: (config?: RequestConfig) => request<Health>("GET", "/health", undefined, config),

  printers: {
    list: (config?: RequestConfig) =>
      request<PrinterState[]>("GET", "/api/printers", undefined, config),

    get: (id: string, config?: RequestConfig) =>
      request<PrinterState>("GET", `/api/printers/${enc(id)}`, undefined, config),

    /** Modeled state + identity + the printer's complete raw report. 404 if unknown. */
    detail: (id: string, config?: RequestConfig) =>
      request<PrinterDetail>("GET", `/api/printers/${enc(id)}/detail`, undefined, config),

    /** Live swap loop. Returns `{ armed: false }` until a job is armed — narrow on `armed`. */
    orchestrator: (id: string, config?: RequestConfig) =>
      request<OrchestratorStatus>(
        "GET",
        `/api/printers/${enc(id)}/orchestrator`,
        undefined,
        config,
      ),

    loadout: {
      /** One row per configured module, with the spool in it (or null when empty). */
      get: (id: string, config?: RequestConfig) =>
        request<LoadoutRow[]>("GET", `/api/printers/${enc(id)}/loadout`, undefined, config),

      set: (id: string, module: string, spoolId: string) =>
        request<OkResponse>("PUT", `/api/printers/${enc(id)}/loadout`, undefined, {
          query: { module, spool_id: spoolId },
        }),
    },
  },

  jobs: {
    /** Upload a sliced `.gcode.3mf`. `start: false` ARMS ONLY — the operator starts the print
     *  themselves and the Brain owns the swap loop from the first pause onward. */
    submit: (printerId: string, file: File, start = true) => {
      const form = new FormData();
      form.append("file", file);
      return request<JobResult>("POST", `/api/printers/${enc(printerId)}/job`, form, {
        query: { start },
      });
    },

    /** Push + start the ALREADY-armed job without re-arming (preserves the confirmed
     *  mapping). Throws ApiError 409 when nothing is armed. */
    start: (printerId: string) =>
      request<StartArmedResult>("POST", `/api/printers/${enc(printerId)}/job/start`),

    assignment: {
      get: (printerId: string, config?: RequestConfig) =>
        request<AssignmentResponse>(
          "GET",
          `/api/printers/${enc(printerId)}/job/assignment`,
          undefined,
          config,
        ),

      /** Confirm (and optionally override) the filament-index → module mapping. The server
       *  keys the body by stringified index, so numeric keys are coerced here. */
      confirm: (printerId: string, mapping: Record<number | string, string>) => {
        const body: Record<string, string> = {};
        for (const [index, moduleId] of Object.entries(mapping)) body[String(index)] = moduleId;
        return request<OkResponse>(
          "POST",
          `/api/printers/${enc(printerId)}/job/assignment`,
          body,
        );
      },
    },
  },

  prompts: {
    /** Human-swap actions the orchestrator is currently blocked on. */
    list: (config?: RequestConfig) =>
      request<Prompt[]>("GET", "/api/prompts", undefined, config),

    answer: (promptId: string, response = "done") =>
      request<AnswerResult>("POST", `/api/prompts/${enc(promptId)}/answer`, undefined, {
        query: { response },
      }),
  },

  spools: {
    list: (includeArchived = false, config?: RequestConfig) =>
      request<Spool[]>("GET", "/api/spools", undefined, {
        ...config,
        query: { include_archived: includeArchived },
      }),

    create: (body: SpoolCreate) => request<Spool>("POST", "/api/spools", body),

    update: (id: string, body: SpoolUpdate) =>
      request<Spool>("PATCH", `/api/spools/${enc(id)}`, body),

    delete: (id: string) => request<DeleteResult>("DELETE", `/api/spools/${enc(id)}`),
  },

  modules: {
    list: (config?: RequestConfig) =>
      request<ModuleInfo[]>("GET", "/api/modules", undefined, config),
  },

  /** Simulate-mode-only test hooks. The server hard-gates these on simulate, so they can
   *  never fire against real hardware — grouped separately so that stays obvious here too. */
  sim: {
    pause: (printerId: string, opts?: { tag?: string; line?: number }) =>
      request<SimPauseResult>("POST", `/api/printers/${enc(printerId)}/sim/pause`, undefined, {
        query: { tag: opts?.tag, line: opts?.line },
      }),

    sensor: (printerId: string, present = true) =>
      request<SimSensorResult>(
        "POST",
        `/api/printers/${enc(printerId)}/sim/sensor`,
        undefined,
        { query: { present } },
      ),
  },
} as const;
