/**
 * What went wrong, in sentences a person can act on.
 *
 * Every failure the page can meet ends here: a server error body, a server
 * that stopped answering, an answer in the wrong shape, a page opened
 * without a session token, or something thrown in the page itself. Each
 * becomes a title, the server's (or the browser's) own message, and one
 * line saying what to do next. The message is never replaced by a vaguer
 * one; "Something went wrong" is not a state this page has.
 */
import { ApiRequestError } from "@/api/client";
import type { ApiError, ErrorCode } from "@/api/types";

import { networkFailureOf, networkSentence, plain, withoutUrls } from "./copy";

export interface ReadableError {
  title: string;
  /**
   * What happened, in plain words: request URLs named by their host, flags
   * named by their field, an upstream outage as "UniProt did not answer".
   * Safe to use as an accessible name or a toast.
   */
  message: string;
  /** The server's or the browser's own text before it was reworded (a disclosure's content, never a name). */
  raw: string;
  /** What to do about it, when the page knows. */
  hint: string | null;
  /** The request field the server named (400 malformed). */
  field: string | null;
  code: ErrorCode | "contract" | "network" | "session" | "page";
  status: number;
}

const TITLES: Record<ErrorCode, string> = {
  malformed: "That question is not well formed",
  unauthorized: "The server refused this page's session",
  forbidden: "The server refused this page",
  not_found: "Not found",
  method_not_allowed: "The server does not do that here",
  conflict: "Not now",
  too_large: "That request is too large",
  unsupported_media_type: "The server did not accept that request",
  unavailable: "Not available in this installation",
  crash: "The server failed on this request",
};

const HINTS: Partial<Record<ErrorCode, string>> = {
  unauthorized:
    "The server was probably restarted since this page loaded, and every launch has a new session. Reload the page.",
  forbidden: "Open the address `caterva studio` printed, rather than this one.",
  crash: "The traceback is in studio.log in the workspace folder (Settings shows where).",
};

/** The sentence for a failure's text: an outage says so, anything else is reworded for the window. */
function plainMessage(text: string): string {
  const outage = networkFailureOf(text);
  return outage ? networkSentence(outage) : plain(withoutUrls(text));
}

export function describeApiError(error: ApiError, status = 0): ReadableError {
  return {
    title: TITLES[error.code] ?? "The request failed",
    message: plainMessage(error.message),
    raw: error.message,
    hint: HINTS[error.code] ?? null,
    field: error.field ?? null,
    code: error.code,
    status,
  };
}

export function describeError(e: unknown): ReadableError {
  if (e instanceof ApiRequestError) {
    if (e.kind === "network") {
      return {
        title: "The studio server is not answering",
        message: e.error.message,
        raw: e.error.message,
        hint: "It may have stopped. In Caterva.app, choose Restart; in a terminal, run `caterva studio` again and open the address it prints.",
        field: null,
        code: "network",
        status: 0,
      };
    }
    if (e.kind === "session") {
      return {
        title: "This page was not opened by the studio server",
        message: e.error.message,
        raw: e.error.message,
        hint: "Start it with `caterva studio`, then open the address it prints (it includes a fresh session).",
        field: null,
        code: "session",
        status: 0,
      };
    }
    if (e.kind === "contract") {
      return {
        title: "The server's answer did not match this page",
        message: e.error.message,
        raw: e.error.message,
        hint: "The page and the server were built from different checkouts. Rebuild the page (`pnpm --filter @workspace/caterva-studio run build`) from the same checkout as the server.",
        field: e.error.field ?? null,
        code: "contract",
        status: e.status,
      };
    }
    return describeApiError(e.error, e.status);
  }
  if (e instanceof Error) {
    const raw = `${e.name}: ${e.message}`;
    return { title: "The page failed", message: plainMessage(raw), raw, hint: null, field: null, code: "page", status: 0 };
  }
  return { title: "The page failed", message: String(e), raw: String(e), hint: null, field: null, code: "page", status: 0 };
}

/** The ApiError a component that takes one should show for any failure. */
export function asApiError(e: unknown): ApiError {
  if (e instanceof ApiRequestError) return e.error;
  const r = describeError(e);
  return { code: "crash", message: r.message };
}
