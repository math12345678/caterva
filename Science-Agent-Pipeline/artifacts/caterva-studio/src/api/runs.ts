/**
 * Runs: submit one, follow its events, read its result, list, delete and
 * export them.
 *
 * Events arrive as Server-Sent Events, read with fetch rather than
 * EventSource, because EventSource cannot add the session header and the
 * session must never ride in a URL (docs/studio/CONTRACT.md 8.4). One
 * stream per run is shared by everything on the page that follows it (the
 * screen showing the run, the job activity in the top bar), so a run is
 * never followed twice. A stream that drops before `end` reconnects with
 * `Last-Event-ID`, and the server sends only what came after it.
 */
import type { ZodType, ZodTypeDef } from "zod";

import { ApiRequestError, apiDelete, apiFetch, apiJson, apiPost, checked, downloadFrom } from "./client";
import {
  EVENT_SCHEMAS,
  ResultObjectSchema,
  RunCreatedSchema,
  RunListSchema,
  RunRecordSchema,
  RunSummarySchema,
} from "@/lib/schemas";
import type {
  EndEvent,
  ErrorEvent,
  EventName,
  LogEvent,
  ResultEvent,
  RunCreated,
  RunKind,
  RunList,
  RunRecord,
  RunRequests,
  RunResults,
  RunStatus,
  RunSummary,
  StageEvent,
  StatusEvent,
} from "./types";

export type RunEvent =
  | { event: "status"; data: StatusEvent }
  | { event: "stage"; data: StageEvent }
  | { event: "log"; data: LogEvent }
  | { event: "result"; data: ResultEvent }
  | { event: "error"; data: ErrorEvent }
  | { event: "end"; data: EndEvent };

const EVENT_NAMES: readonly EventName[] = ["status", "stage", "log", "result", "error", "end"];

/** A run that will not change again. */
export const TERMINAL: ReadonlySet<RunStatus> = new Set(["done", "failed", "cancelled", "interrupted"]);

export function isTerminal(status: RunStatus | "idle"): boolean {
  return status !== "idle" && TERMINAL.has(status);
}

const runPath = (id: string) => `/api/runs/${encodeURIComponent(id)}`;

export function createRun<K extends RunKind>(kind: K, request: RunRequests[K], title?: string): Promise<RunCreated> {
  return apiPost<RunCreated>("/api/runs", title ? { kind, request, title } : { kind, request }, RunCreatedSchema);
}

export function getRun(id: string): Promise<RunRecord> {
  return apiJson<RunRecord>(runPath(id), {}, RunRecordSchema);
}

export async function getResult<K extends RunKind>(id: string): Promise<RunResults[K]> {
  // Checked only as an object: the kind's owner knows the rest of its shape.
  const body = await apiJson<Record<string, unknown>>(`${runPath(id)}/result`, {}, ResultObjectSchema);
  return body as unknown as RunResults[K];
}

export function cancelRun(id: string): Promise<RunRecord> {
  return apiPost<RunRecord>(`${runPath(id)}/cancel`, {}, RunRecordSchema);
}

export function deleteRun(id: string): Promise<RunSummary> {
  return apiDelete<RunSummary>(runPath(id), RunSummarySchema);
}

export interface ListRunsQuery {
  kind?: RunKind;
  status?: RunStatus;
  limit?: number;
  cursor?: string | null;
}

export function listRuns(query: ListRunsQuery = {}): Promise<RunList> {
  const params = new URLSearchParams();
  if (query.kind) params.set("kind", query.kind);
  if (query.status) params.set("status", query.status);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.cursor) params.set("cursor", query.cursor);
  const qs = params.toString();
  return apiJson<RunList>(qs ? `/api/runs?${qs}` : "/api/runs", {}, RunListSchema);
}

/** Save one of a run's recorded files. */
export function downloadArtifact(id: string, name: string): Promise<string> {
  return downloadFrom(`${runPath(id)}/artifacts/${encodeURIComponent(name)}`, name);
}

/** Save a run as caterva-<id>.zip: the record, request, result, events, artifacts and the command. */
export function downloadBundle(id: string): Promise<string> {
  return downloadFrom(`${runPath(id)}/bundle`, `caterva-${id}.zip`);
}

/** Parse one SSE block ("event: x\nid: n\ndata: {...}") into a checked RunEvent. */
export function parseEventBlock(block: string): RunEvent | null {
  let name = "";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") name = value;
    else if (field === "data") data.push(value);
  }
  if (!EVENT_NAMES.includes(name as EventName) || data.length === 0) return null;
  const eventName = name as EventName;
  let parsed: unknown;
  try {
    parsed = JSON.parse(data.join("\n"));
  } catch {
    throw new ApiRequestError(
      200,
      { code: "crash", message: `A ${eventName} event from the server was not JSON.` },
      "contract",
    );
  }
  const schema: ZodType<unknown, ZodTypeDef, unknown> = EVENT_SCHEMAS[eventName];
  return { event: eventName, data: checked(`the ${eventName} event`, parsed, schema) } as RunEvent;
}

/**
 * Read a run's event stream until `end` or until the server closes it.
 * Resolves "ended" after `end`, "closed" when the stream stopped first.
 * With `afterSeq`, only events after that sequence number are sent.
 */
export async function followRun(
  id: string,
  onEvent: (event: RunEvent) => void,
  signal?: AbortSignal,
  afterSeq?: number,
): Promise<"ended" | "closed"> {
  const headers: Record<string, string> = { Accept: "text/event-stream" };
  if (afterSeq !== undefined && afterSeq > 0) headers["Last-Event-ID"] = String(afterSeq);
  const response = await apiFetch(`${runPath(id)}/events`, { headers, signal });
  if (!response.body) return "closed";
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return "closed";
      buffer += value.replace(/\r\n?/g, "\n");
      let cut = buffer.indexOf("\n\n");
      while (cut !== -1) {
        const parsed = parseEventBlock(buffer.slice(0, cut));
        buffer = buffer.slice(cut + 2);
        if (parsed) {
          onEvent(parsed);
          if (parsed.event === "end") return "ended";
        }
        cut = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ---------------------------------------------------------------- streams

export interface StreamListener {
  onEvent(event: RunEvent): void;
  /** The stream could not be followed (the run was deleted, the server stopped for good). */
  onError?(error: ApiRequestError): void;
}

const RETRY_DELAYS_MS = [500, 1000, 2000, 4000, 8000];

/** One run's events, followed once and shared by every listener on the page. */
export class RunStream {
  readonly runId: string;
  readonly events: RunEvent[] = [];
  ended = false;
  failure: ApiRequestError | null = null;
  private lastSeq = 0;
  private listeners = new Set<StreamListener>();
  private controller = new AbortController();
  private started = false;
  private readonly onIdle: (stream: RunStream) => void;

  constructor(runId: string, onIdle: (stream: RunStream) => void) {
    this.runId = runId;
    this.onIdle = onIdle;
  }

  /** Listen from the start: past events are replayed, then live ones delivered. */
  subscribe(listener: StreamListener): () => void {
    this.listeners.add(listener);
    for (const e of this.events) listener.onEvent(e);
    if (this.failure) listener.onError?.(this.failure);
    if (!this.started) {
      this.started = true;
      void this.run();
    }
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) {
        if (!this.ended) this.controller.abort();
        this.onIdle(this);
      }
    };
  }

  private deliver(event: RunEvent): void {
    if (event.data.seq <= this.lastSeq) return; // a replay after reconnecting
    this.lastSeq = event.data.seq;
    this.events.push(event);
    if (event.event === "end") this.ended = true;
    for (const l of this.listeners) l.onEvent(event);
  }

  private fail(error: ApiRequestError): void {
    this.failure = error;
    for (const l of this.listeners) l.onError?.(error);
  }

  private async run(): Promise<void> {
    let attempt = 0;
    const signal = this.controller.signal;
    while (!this.ended && !signal.aborted) {
      try {
        const how = await followRun(this.runId, (e) => this.deliver(e), signal, this.lastSeq);
        if (how === "ended") return;
        attempt = 0; // it was working; a close is a reason to reconnect, not to give up
      } catch (e) {
        if (signal.aborted) return;
        const error =
          e instanceof ApiRequestError
            ? e
            : new ApiRequestError(0, { code: "unavailable", message: String(e) }, "network");
        // Only a dropped connection is worth retrying; a refusal will not change.
        if (error.kind !== "network" || attempt >= RETRY_DELAYS_MS.length) {
          this.fail(error);
          return;
        }
      }
      const delay = RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)];
      attempt += 1;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
}

const streams = new Map<string, RunStream>();

/** Follow a run's events; the returned function stops listening. */
export function subscribeToRun(runId: string, listener: StreamListener): () => void {
  let stream = streams.get(runId);
  if (!stream) {
    stream = new RunStream(runId, (idle) => {
      if (streams.get(idle.runId) === idle) streams.delete(idle.runId);
    });
    streams.set(runId, stream);
  }
  return stream.subscribe(listener);
}

/** For tests: forget every stream. */
export function resetRunStreamsForTests(): void {
  streams.clear();
}
