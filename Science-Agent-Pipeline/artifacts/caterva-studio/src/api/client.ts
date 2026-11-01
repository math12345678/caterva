/**
 * The one way the page talks to `caterva studio`.
 *
 * Every /api/ request carries the per-launch session token in a header,
 * never in a path or query string. The server puts the token in no document
 * it serves: it arrives in the URL FRAGMENT of the address the launcher
 * opens (`http://127.0.0.1:<port>/#token=<token>`), which a browser never
 * sends to a server. `sessionToken()` reads it from `location.hash` the
 * first time it is asked (at import, before anything renders), keeps it in
 * memory and in this tab's sessionStorage so a reload keeps working, and
 * removes the fragment from the address bar at once. A page opened without
 * one (and with none remembered) has no token: `sessionToken()` returns
 * null so the shell can say so rather than make requests that will all be
 * refused.
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

import { type ApiError, SESSION_HEADER, TOKEN_FRAGMENT_KEY } from "./types";

let cachedToken: string | null | undefined;

const STORAGE_KEY = "caterva.studio.session";
const TOKEN_SHAPE = /^[A-Za-z0-9_-]{16,128}$/;
/** The development server writes the backend's token in this tag; a build never has it. */
const DEV_META = "caterva-dev-session";

function fromFragment(): string | null {
  const hash = window.location.hash;
  if (hash.length < 2) return null;
  const params = new URLSearchParams(hash.slice(1));
  const value = params.get(TOKEN_FRAGMENT_KEY);
  if (value === null) return null;
  params.delete(TOKEN_FRAGMENT_KEY);
  const rest = params.toString();
  // The fragment is removed whether or not the token in it is usable, so it
  // never sits in the address bar, history or a copied link.
  try {
    window.history.replaceState(
      window.history.state,
      "",
      `${window.location.pathname}${window.location.search}${rest ? `#${rest}` : ""}`,
    );
  } catch {
    // An address that cannot be rewritten leaves the fragment; the token still works.
  }
  return TOKEN_SHAPE.test(value) ? value : null;
}

function remembered(): string | null {
  try {
    const value = window.sessionStorage.getItem(STORAGE_KEY);
    return value && TOKEN_SHAPE.test(value) ? value : null;
  } catch {
    return null;
  }
}

function remember(value: string | null): void {
  try {
    if (value === null) window.sessionStorage.removeItem(STORAGE_KEY);
    else window.sessionStorage.setItem(STORAGE_KEY, value);
  } catch {
    // Storage can be unavailable; the token then lives in memory for this load only.
  }
}

export function sessionToken(): string | null {
  if (cachedToken !== undefined) return cachedToken;
  let value = fromFragment();
  if (value !== null) remember(value);
  else value = remembered();
  if (value === null && import.meta.env.DEV) {
    const meta = document.querySelector<HTMLMetaElement>(`meta[name="${DEV_META}"]`);
    const content = meta?.content ?? "";
    value = TOKEN_SHAPE.test(content) ? content : null;
  }
  cachedToken = value;
  return cachedToken;
}

/** The server refused the token (a page left open across a restart, or a
 * stale one remembered by this tab): forget it, so the shell says to reopen
 * the address the studio printed rather than retrying with it. */
export function discardSessionToken(): void {
  remember(null);
  cachedToken = null;
}

/** Hand the page a token directly, or none. For tests. */
export function adoptSessionTokenForTests(token: string | null): void {
  remember(null);
  cachedToken = token;
}

/** Forget the token read from the page, so the next request reads it again. For tests. */
export function resetSessionTokenForTests(): void {
  cachedToken = undefined;
}

// Read the fragment before anything renders or any router can see it.
if (typeof window !== "undefined") sessionToken();

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
  "This page was opened without a session token. Open the address `caterva studio` prints, including the part after the #, or use the app.";

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
  if (response.status === 401) discardSessionToken();
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
