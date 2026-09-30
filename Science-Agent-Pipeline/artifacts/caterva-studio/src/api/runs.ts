/**
 * Runs: submit one, follow its events, read its result.
 *
 * Events arrive as Server-Sent Events, read with fetch rather than
 * EventSource because EventSource cannot send the session header, and the
 * token must never ride in a URL (docs/studio/CONTRACT.md, "Jobs and events").
 */
import { apiFetch, apiJson, apiPost } from "./client";
import type {
  EndEvent,
  ErrorEvent,
  EventName,
  LogEvent,
  ResultEvent,
  RunCreated,
  RunKind,
  RunRecord,
  RunRequests,
  RunResults,
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

export function createRun<K extends RunKind>(
  kind: K,
  request: RunRequests[K],
  title?: string,
): Promise<RunCreated> {
  return apiPost<RunCreated>("/api/runs", title ? { kind, request, title } : { kind, request });
}

export function getRun(id: string): Promise<RunRecord> {
  return apiJson<RunRecord>(`/api/runs/${encodeURIComponent(id)}`);
}

export function getResult<K extends RunKind>(id: string): Promise<RunResults[K]> {
  return apiJson<RunResults[K]>(`/api/runs/${encodeURIComponent(id)}/result`);
}

export function cancelRun(id: string): Promise<RunRecord> {
  return apiPost<RunRecord>(`/api/runs/${encodeURIComponent(id)}/cancel`, {});
}

/** Parse one SSE block ("event: x\nid: n\ndata: {...}") into a RunEvent. */
export function parseEventBlock(block: string): RunEvent | null {
  let name = "";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") name = value;
    else if (field === "data") data.push(value);
  }
  if (!EVENT_NAMES.includes(name as EventName) || data.length === 0) return null;
  return { event: name as EventName, data: JSON.parse(data.join("\n")) } as RunEvent;
}

/**
 * Follow a run's events until `end`, calling `onEvent` for each. Replays
 * from the start (the server keeps every event), so a page opened on a
 * finished run sees its whole history.
 */
export async function followRun(
  id: string,
  onEvent: (event: RunEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await apiFetch(`/api/runs/${encodeURIComponent(id)}/events`, {
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (!response.body) return;
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replace(/\r\n/g, "\n");
    let cut = buffer.indexOf("\n\n");
    while (cut !== -1) {
      const parsed = parseEventBlock(buffer.slice(0, cut));
      buffer = buffer.slice(cut + 2);
      if (parsed) {
        onEvent(parsed);
        if (parsed.event === "end") return;
      }
      cut = buffer.indexOf("\n\n");
    }
  }
}
