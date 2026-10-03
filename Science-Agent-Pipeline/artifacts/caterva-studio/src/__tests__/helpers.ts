/**
 * A stand-in for the studio server in tests: `fetch` answered from the real
 * recorded answers in fixtures/api (or from a handler), every request
 * recorded so a test can check the session header and the body it sent.
 */
import { vi } from "vitest";

import { adoptSessionTokenForTests } from "@/api/client";

export interface Recorded {
  status: number;
  body: unknown;
}

export interface SeenRequest {
  url: string;
  method: string;
  headers: Headers;
  body: unknown;
}

export type Handler = (req: SeenRequest) => Response | Promise<Response> | Recorded | undefined;

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export function fromRecorded(r: Recorded): Response {
  return json(r.status, r.body);
}

/** Give the page a session token, as the address the launcher opens does (or none). */
export function setSessionToken(token: string | null): void {
  adoptSessionTokenForTests(token);
}

export function mockServer(handler: Handler) {
  const seen: SeenRequest[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const headers = new Headers(init.headers);
    let body: unknown = undefined;
    if (typeof init.body === "string") {
      try {
        body = JSON.parse(init.body);
      } catch {
        body = init.body;
      }
    }
    const req = { url, method: (init.method ?? "GET").toUpperCase(), headers, body };
    seen.push(req);
    const answer = await handler(req);
    if (answer === undefined) return json(404, { error: { code: "not_found", message: `no handler for ${req.method} ${url}` } });
    return answer instanceof Response ? answer : fromRecorded(answer);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { seen, fetchMock };
}

/** An SSE body that arrives in the given chunks, as a server flushing frames would send it. */
export function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

/** One SSE frame in the contract's format (CONTRACT.md 8.4). */
export function frame(event: string, seq: number, data: Record<string, unknown>): string {
  return `id: ${seq}\nevent: ${event}\ndata: ${JSON.stringify({ seq, ...data })}\n\n`;
}

/**
 * Parse the committed SSA CSV into the columns a SimResult carries. Python's
 * csv module ends rows with CRLF, so both line endings are accepted.
 */
export function parseCsv(text: string): { columns: string[]; series: Record<string, number[]> } {
  const [head, ...lines] = text.trim().split(/\r?\n/);
  const columns = head.split(",");
  const series: Record<string, number[]> = Object.fromEntries(columns.map((c) => [c, []]));
  for (const line of lines) {
    line.split(",").forEach((cell, i) => series[columns[i]].push(Number(cell)));
  }
  return { columns, series };
}

/**
 * A text matcher for a run's title in a list. The title is drawn with its
 * identifiers ("EC 1.1.1.27") in their own spans, so the text is split across
 * elements; this matches the title element by its whole text.
 */
export const runTitle = (text: string) => (_content: string, element: Element | null): boolean =>
  Boolean(element && element.matches(".run-row-title") && element.textContent === text);
