/**
 * The one way the page talks to `caterva studio`.
 *
 * Every /api/ request carries the per-launch session token in a header
 * (never in a URL, where it would land in logs and history). The token is
 * read once from the <meta> tag the server wrote into index.html; a page
 * whose tag still holds the placeholder was not served by the studio, and
 * `sessionToken()` returns null so the shell can say so instead of sending
 * requests that will all be refused.
 */
import {
  type ApiError,
  type ErrorBody,
  SESSION_HEADER,
  SESSION_META_NAME,
  TOKEN_PLACEHOLDER,
} from "./types";

let cachedToken: string | null | undefined;

export function sessionToken(): string | null {
  if (cachedToken !== undefined) return cachedToken;
  const meta = document.querySelector<HTMLMetaElement>(`meta[name="${SESSION_META_NAME}"]`);
  const value = meta?.content ?? "";
  cachedToken = value && value !== TOKEN_PLACEHOLDER ? value : null;
  return cachedToken;
}

/** A request the server answered with an error body, or could not answer. */
export class ApiRequestError extends Error {
  readonly status: number;
  readonly error: ApiError;

  constructor(status: number, error: ApiError) {
    super(error.message);
    this.name = "ApiRequestError";
    this.status = status;
    this.error = error;
  }
}

function isErrorBody(body: unknown): body is ErrorBody {
  return (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    typeof (body as { error: { message?: unknown } }).error?.message === "string"
  );
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = sessionToken();
  if (token === null) {
    throw new ApiRequestError(0, {
      code: "unauthorized",
      message:
        "This page was not served by `caterva studio`, so it has no session token. Open the address `caterva studio` prints.",
    });
  }
  const headers = new Headers(init.headers);
  headers.set(SESSION_HEADER, token);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  } catch (cause) {
    throw new ApiRequestError(0, {
      code: "unavailable",
      message: `The studio server did not answer (${String(cause)}). It may have stopped.`,
    });
  }
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new ApiRequestError(
      response.status,
      isErrorBody(body)
        ? body.error
        : { code: "crash", message: `HTTP ${response.status} with no error body` },
    );
  }
  return response;
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  return (await response.json()) as T;
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiJson<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return apiJson<T>(path, { method: "PUT", body: JSON.stringify(body) });
}
