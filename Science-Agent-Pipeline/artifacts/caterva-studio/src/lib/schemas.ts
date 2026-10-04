/**
 * Runtime checks on what the server sends, for the shapes the page itself
 * depends on (docs/studio/CONTRACT.md sections 7 to 10).
 *
 * src/api/types.ts says what the server promises; nothing checks a promise
 * at run time. A page built from one checkout talking to a server from
 * another would read a renamed field as `undefined` and draw it as an empty
 * cell, which here is the worst failure: a number silently absent looks
 * exactly like a number nobody measured. So every core response goes
 * through one of these before a screen sees it, and a mismatch becomes a
 * readable "the server's answer did not match this page" rather than a
 * blank.
 *
 * Objects are `.passthrough()`: a key the page does not know yet is kept,
 * never dropped, because dropping data silently is the defect this file
 * exists to prevent. Each schema is pinned to its TypeScript type below, so
 * the two cannot drift apart without a compile error.
 *
 * Kind results (ComposeResult, ...) are checked here only as "an object";
 * their owners validate their own sections if they choose to.
 */
import { z } from "zod";

import type {
  ApiError,
  Capabilities,
  Citation,
  DevSession,
  EndEvent,
  ErrorBody,
  ErrorEvent,
  Health,
  LogEvent,
  Outcome,
  Provenance,
  ResultEvent,
  RunCreated,
  RunList,
  RunRecord,
  RunSummary,
  Settings,
  SourcedValue,
  StageEvent,
  StatusEvent,
} from "@/api/types";

export const RunKindSchema = z.enum([
  "compose",
  "constants",
  "sim",
  "bind",
  "structure",
  "prepare",
  "md.setup",
  "md.summarise",
  "analyze",
  "fep.status",
  "complex.check",
  "rates",
]);
export const RunStatusSchema = z.enum([
  "queued",
  "running",
  "cancelling",
  "done",
  "failed",
  "cancelled",
  "abandoned",
  "interrupted",
]);
export const OutcomeMeaningSchema = z.enum(["produced", "refused", "negative", "network"]);
export const ProvenanceKindSchema = z.enum(["measured", "fitted", "computed", "placeholder", "chosen"]);
export const ErrorCodeSchema = z.enum([
  "malformed",
  "unauthorized",
  "forbidden",
  "not_found",
  "method_not_allowed",
  "conflict",
  "too_large",
  "unsupported_media_type",
  "unavailable",
  "crash",
]);
export const ThemeSchema = z.enum(["system", "light", "dark"]);
export const NeedSchema = z.enum(["network", "literature", "gromacs"]);

// --------------------------------------------------------------- provenance

export const CitationSchema = z
  .object({
    text: z.string(),
    registry: z.string().nullable().optional(),
    reference_id: z.string().nullable().optional(),
    url: z.string().nullable().optional(),
    title: z.string().nullable().optional(),
    journal: z.string().nullable().optional(),
    year: z.number().nullable().optional(),
    doi: z.string().nullable().optional(),
    pubmed: z.string().nullable().optional(),
    via: z.string().nullable().optional(),
  })
  .passthrough();

export const ProvenanceSchema = z
  .object({
    kind: ProvenanceKindSchema,
    citation: CitationSchema.optional(),
    organism: z.string().nullable().optional(),
    cross_species: z.boolean().optional(),
    conditions: z
      .object({
        ph: z.number().nullable(),
        temperature_c: z.number().nullable(),
        buffer: z.string().nullable(),
        unreported: z.array(z.string()),
      })
      .passthrough()
      .optional(),
    commentary: z.string().nullable().optional(),
    scope: z.array(z.string()).optional(),
    spread: z
      .object({
        low: z.number(),
        high: z.number(),
        unit: z.string(),
        carried: z.number(),
        n_values: z.number(),
        references: z.array(z.string()),
        sentence: z.string(),
      })
      .passthrough()
      .nullable()
      .optional(),
    chosen_because: z.string().nullable().optional(),
    reason: z.string().nullable().optional(),
    table: z.string().nullable().optional(),
    method: z.string().nullable().optional(),
    inputs: z.array(z.string()).optional(),
    fit: z
      .object({
        method: z.string(),
        n_points: z.number().nullable().optional(),
        residual: z.number().nullable().optional(),
        stderr: z.number().nullable().optional(),
        r_squared: z.number().nullable().optional(),
      })
      .passthrough()
      .optional(),
    by: z.enum(["user", "default"]).optional(),
    note: z.string().nullable().optional(),
  })
  .passthrough();

export const SourcedValueSchema = z
  .object({
    value: z.number().nullable(),
    unit: z.string(),
    provenance: ProvenanceSchema,
    id: z.string().optional(),
    label: z.string().optional(),
    nonfinite: z.enum(["nan", "inf", "-inf"]).optional(),
    interval: z
      .object({ low: z.number().nullable(), high: z.number().nullable(), meaning: z.string() })
      .passthrough()
      .optional(),
  })
  .passthrough();

// ------------------------------------------------------------------- errors

export const ApiErrorSchema = z
  .object({
    code: ErrorCodeSchema,
    message: z.string(),
    field: z.string().nullable().optional(),
    details: z.record(z.unknown()).optional(),
  })
  .passthrough();

export const ErrorBodySchema = z.object({ error: ApiErrorSchema }).passthrough();

// --------------------------------------------------------------------- meta

export const HealthSchema = z
  .object({ ok: z.boolean(), version: z.string(), api_version: z.number(), started_at: z.string() })
  .passthrough();

const available = z.object({ available: z.boolean(), reason: z.string().nullable() }).passthrough();

export const CapabilitiesSchema = z
  .object({
    version: z.string(),
    api_version: z.number(),
    python: z.string(),
    platform: z.string(),
    frozen: z.boolean(),
    literature: available,
    network: z
      .object({
        checked: z.boolean(),
        reachable: z.boolean().nullable(),
        hosts: z.record(z.boolean().nullable()),
        host_status: z
          .record(
            z.object({
              reachable: z.boolean().nullable(),
              checked_at: z.string().nullable(),
              source: z.string().nullable(),
              reason: z.string().nullable(),
            }),
          )
          .default({}),
        checked_at: z.string().nullable(),
        reason: z.string().nullable(),
        source: z.string().nullable().default(null),
      })
      .passthrough(),
    gromacs: z
      .object({
        found: z.boolean(),
        path: z.string().nullable(),
        version: z.string().nullable(),
        reason: z.string().nullable(),
      })
      .passthrough(),
    rates: available,
    ui: z.object({ built: z.boolean(), static_dir: z.string(), reason: z.string().nullable() }).passthrough(),
    data_dir: z
      .object({ path: z.string(), writable: z.boolean(), runs: z.number(), reason: z.string().nullable() })
      .passthrough(),
    kinds: z.record(
      z
        .object({
          available: z.boolean(),
          title: z.string(),
          command: z.string(),
          needs: z.array(NeedSchema),
          reason: z.string().nullable(),
        })
        .passthrough(),
    ),
    dev_origin: z.string().nullable(),
  })
  .passthrough();

export const SettingsSchema = z
  .object({ theme: ThemeSchema, max_parallel_runs: z.number(), confirm_delete: z.boolean() })
  .passthrough();

export const DevSessionSchema = z.object({ token: z.string(), api_version: z.number() }).passthrough();

// ---------------------------------------------------------------------- runs

export const OutcomeSchema = z
  .object({
    exit_code: z.number(),
    meaning: OutcomeMeaningSchema,
    summary: z.string(),
    reason: z.string().nullable(),
  })
  .passthrough();

export const RunErrorSchema = z
  .object({ type: z.string(), message: z.string(), traceback: z.string().nullable().optional() })
  .passthrough();

export const RunRecordSchema = z
  .object({
    schema: z.string(),
    id: z.string(),
    kind: RunKindSchema,
    title: z.string(),
    status: RunStatusSchema,
    created_at: z.string(),
    started_at: z.string().nullable(),
    finished_at: z.string().nullable(),
    caterva_version: z.string(),
    cli: z.array(z.string()),
    request: z.record(z.unknown()),
    outcome: OutcomeSchema.nullable(),
    error: RunErrorSchema.nullable(),
    artifacts: z.array(
      z
        .object({ name: z.string(), content_type: z.string(), bytes: z.number(), description: z.string() })
        .passthrough(),
    ),
    progress: z
      .object({ stage: z.string(), label: z.string(), fraction: z.number().nullable() })
      .passthrough()
      .nullable(),
  })
  .passthrough();

export const RunSummarySchema = z
  .object({
    id: z.string(),
    kind: RunKindSchema,
    title: z.string(),
    status: RunStatusSchema,
    created_at: z.string(),
    finished_at: z.string().nullable(),
    outcome: OutcomeSchema.nullable(),
  })
  .passthrough();

export const RunListSchema = z
  .object({ runs: z.array(RunSummarySchema), next_cursor: z.string().nullable() })
  .passthrough();

export const RunCreatedSchema = z.object({ run: RunRecordSchema }).passthrough();

/** A kind's Result, checked only as a JSON object; its owner knows its shape. */
export const ResultObjectSchema = z.record(z.unknown());

// -------------------------------------------------------------------- events

const eventBase = { run_id: z.string(), seq: z.number(), at: z.string() };

export const StatusEventSchema = z
  .object({ ...eventBase, status: RunStatusSchema, outcome: OutcomeSchema.nullable().optional() })
  .passthrough();
export const StageEventSchema = z
  .object({ ...eventBase, stage: z.string(), label: z.string(), fraction: z.number().nullable() })
  .passthrough();
export const LogEventSchema = z.object({ ...eventBase, line: z.string() }).passthrough();
export const ResultEventSchema = z.object({ ...eventBase, outcome: OutcomeSchema }).passthrough();
export const ErrorEventSchema = z.object({ ...eventBase, error: RunErrorSchema }).passthrough();
export const EndEventSchema = z.object({ ...eventBase, status: RunStatusSchema }).passthrough();

export const EVENT_SCHEMAS = {
  status: StatusEventSchema,
  stage: StageEventSchema,
  log: LogEventSchema,
  result: ResultEventSchema,
  error: ErrorEventSchema,
  end: EndEventSchema,
} as const;

// ------------------------------------------------------------------ pinning
// Each line fails to compile if the schema and the contract's type differ in
// a way that would let a checked value be the wrong shape.

type Pin<T> = z.ZodType<T, z.ZodTypeDef, unknown>;
export const PINNED = {
  citation: CitationSchema satisfies Pin<Citation>,
  provenance: ProvenanceSchema satisfies Pin<Provenance>,
  sourcedValue: SourcedValueSchema satisfies Pin<SourcedValue>,
  apiError: ApiErrorSchema satisfies Pin<ApiError>,
  errorBody: ErrorBodySchema satisfies Pin<ErrorBody>,
  health: HealthSchema satisfies Pin<Health>,
  capabilities: CapabilitiesSchema satisfies Pin<Capabilities>,
  settings: SettingsSchema satisfies Pin<Settings>,
  devSession: DevSessionSchema satisfies Pin<DevSession>,
  outcome: OutcomeSchema satisfies Pin<Outcome>,
  runRecord: RunRecordSchema satisfies Pin<RunRecord>,
  runSummary: RunSummarySchema satisfies Pin<RunSummary>,
  runList: RunListSchema satisfies Pin<RunList>,
  runCreated: RunCreatedSchema satisfies Pin<RunCreated>,
  statusEvent: StatusEventSchema satisfies Pin<StatusEvent>,
  stageEvent: StageEventSchema satisfies Pin<StageEvent>,
  logEvent: LogEventSchema satisfies Pin<LogEvent>,
  resultEvent: ResultEventSchema satisfies Pin<ResultEvent>,
  errorEvent: ErrorEventSchema satisfies Pin<ErrorEvent>,
  endEvent: EndEventSchema satisfies Pin<EndEvent>,
};
