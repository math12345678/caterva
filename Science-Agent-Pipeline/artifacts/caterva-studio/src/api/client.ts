/**
 * The one way the page talks to `caterva studio`.
 *
 * Every /api/ request carries the per-launch session token in a header,
 * never in a URL, where it would land in logs and history. The token is
 * read once from the <meta> tag the server wrote into index.html; a page
 * whose tag still holds the placeholder was not served by the studio, and
 * `sessionToken()` returns null so the shell can say so rather than make
 * requests that will all be refused.
 *
 * A response the page depends on is checked against its schema
 * (src/lib/schemas.ts) before anyone reads it. Four ways a request can go
 * wrong are kept apart, because each needs a different sentence on screen:
 * the server answered with an error body (`server`), it did not answer at
 * all (`network`), it answered in a shape this page does not understand
 * (`contract`), or the page has no session token (`session`).
 */
import type { ZodType, ZodTypeDef } from "zod";

import { ErrorBodySchema } from "@/lib/schemas";

import { type ApiError, SESSION_HEADER, SESSION_META_NAME, TOKEN_PLACEHOLDER } from "./types";

let cachedToken: string | null | undefined;

export function sessionToken(): string | null {
  if (cachedToken !== undefined) return cachedToken;
  const meta = document.querySelector<HTMLMetaElement>(`meta[name="${SESSION_META_NAME}"]`);
  const value = meta?.content ?? "";
  cachedToken = value && value !== TOKEN_PLACEHOLDER ? value : null;
  return cachedToken;
}

/** Forget the token read from the page, so the next request reads it again. For tests. */
export function resetSessionTokenForTests(): void {
  cachedToken = undefined;
}

export type FailureKind = "server" | "network" | "contract" | "session";

/** A request the server answered with an error body, or could not answer. */
export class ApiRequestError extends Error {
  readonly status: number;
  readonly error: ApiError;
  readonly kind: FailureKind;

  constructor(status: number, error: ApiError, kind: FailureKind = "server") {
    super(error.message);
    this.name = "ApiRequestError";
    this.status = status;
    this.error = error;
    this.kind = kind;
  }
}

export const NO_SESSION_MESSAGE =
  "This page was not served by `caterva studio`, so it has no session token. Open the address `caterva studio` prints.";

async function errorFrom(response: Response): Promise<ApiRequestError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const parsed = ErrorBodySchema.safeParse(body);
  if (parsed.success) return new ApiRequestError(response.status, parsed.data.error, "server");
  return new ApiRequestError(
    response.status,
    { code: "crash", message: `The server answered HTTP ${response.status} without an error body.` },
    "server",
  );
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = sessionToken();
  if (token === null) {
    throw new ApiRequestError(0, { code: "unauthorized", message: NO_SESSION_MESSAGE }, "session");
  }
  const headers = new Headers(init.headers);
  headers.set(SESSION_HEADER, token);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers, credentials: "same-origin", cache: "no-store" });
  } catch (cause) {
    if (init.signal?.aborted) throw cause;
    throw new ApiRequestError(
      0,
      {
        code: "unavailable",
        message: `The studio server did not answer (${cause instanceof Error ? cause.message : String(cause)}).`,
      },
      "network",
    );
  }
  if (!response.ok) throw await errorFrom(response);
  return response;
}

/** Check a parsed body against its schema; a mismatch is a `contract` failure naming the first bad field. */
export function checked<T>(path: string, body: unknown, schema: ZodType<T, ZodTypeDef, unknown>): T {
  const parsed = schema.safeParse(body);
  if (parsed.success) return parsed.data;
  const issue = parsed.error.issues[0];
  const where = issue?.path.length ? issue.path.join(".") : "(the whole answer)";
  throw new ApiRequestError(
    200,
    {
      code: "crash",
      message: `The server's answer to ${path} did not match this page at ${where}: ${issue?.message ?? "unknown difference"}.`,
      field: issue?.path.length ? issue.path.join(".") : null,
      details: { issues: parsed.error.issues.slice(0, 5) },
    },
    "contract",
  );
}

/**
 * GET (or any method) and parse JSON. With a schema the body is checked
 * first; without one it is returned as the server sent it, typed by the
 * caller (the science screens' own results).
 */
export async function apiJson<T>(
  path: string,
  init: RequestInit = {},
  schema?: ZodType<T, ZodTypeDef, unknown>,
): Promise<T> {
  const response = await apiFetch(path, init);
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiRequestError(
      response.status,
      { code: "crash", message: `The server's answer to ${path} was not JSON.` },
      "contract",
    );
  }
  return schema ? checked(path, body, schema) : (body as T);
}

export function apiPost<T>(path: string, body: unknown, schema?: ZodType<T, ZodTypeDef, unknown>): Promise<T> {
  return apiJson<T>(path, { method: "POST", body: JSON.stringify(body) }, schema);
}

export function apiPut<T>(path: string, body: unknown, schema?: ZodType<T, ZodTypeDef, unknown>): Promise<T> {
  return apiJson<T>(path, { method: "PUT", body: JSON.stringify(body) }, schema);
}

export function apiDelete<T>(path: string, schema?: ZodType<T, ZodTypeDef, unknown>): Promise<T> {
  return apiJson<T>(path, { method: "DELETE" }, schema);
}

/**
 * Fetch a file the server offers as an attachment (an artifact, a run's
 * bundle) and hand it to the browser as a download. The token rides in the
 * header, so a plain <a href> cannot do this; the file becomes a Blob URL,
 * which the macOS shell turns into a save panel (CONTRACT.md section 16).
 */
export async function downloadFrom(path: string, fallbackName: string): Promise<string> {
  const response = await apiFetch(path);
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const named = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = named;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    // Long enough for the browser (or the shell's download delegate) to start reading it.
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }
  return named;
}
