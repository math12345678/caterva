/**
 * The enzyme finder's two endpoints (docs/studio/CONTRACT.md 7,
 * `GET /api/enzymes/find` and `GET /api/enzymes/{ec}`), and the few pure
 * rules the page needs to read their answers.
 *
 * The server answers from an index in memory, so a query costs
 * milliseconds; the page still waits a moment after the last keystroke so
 * a name typed quickly is one question, not nine. Nothing here chooses an
 * enzyme: `EnzymeFinder` shows what the finder returned and the person
 * chooses.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { ApiRequestError, apiJson } from "./client";
import type { EnzymeCandidate, EnzymeDetail, EnzymeFindResponse } from "./types";

/** A complete EC number, preliminary ones included ("3.2.1.n3"), as the server's `{ec}` route reads it. */
const COMPLETE_EC = /^\d{1,2}\.\d{1,2}\.\d{1,3}\.(?:n?\d{1,4})$/;

export function isCompleteEc(text: string): boolean {
  return COMPLETE_EC.test(text.trim());
}

/** The server's limits (caterva/studio/adapters/enzymes.py). */
export const MAX_QUERY_CHARS = 200;
export const FIND_LIMIT = 10;

export function findPath(q: string, organism: string, limit = FIND_LIMIT): string {
  const params = new URLSearchParams({ q: q.slice(0, MAX_QUERY_CHARS) });
  if (organism.trim()) params.set("organism", organism.trim().slice(0, 100));
  params.set("limit", String(limit));
  return `/api/enzymes/find?${params.toString()}`;
}

export function detailPath(ec: string, organism: string): string {
  const params = new URLSearchParams();
  if (organism.trim()) params.set("organism", organism.trim().slice(0, 100));
  const query = params.toString();
  return `/api/enzymes/${encodeURIComponent(ec)}${query ? `?${query}` : ""}`;
}

export function useEnzymeFind(q: string, organism: string, enabled: boolean) {
  return useQuery({
    queryKey: ["enzymes", "find", q, organism],
    queryFn: () => apiJson<EnzymeFindResponse>(findPath(q, organism)),
    enabled: enabled && q.length > 0,
    // The nomenclature does not change under a running server.
    staleTime: Infinity,
    // Typing on: keep the last list in view until the next one arrives.
    placeholderData: keepPreviousData,
  });
}

/** One enzyme, with the organism's isozymes. A 404 (a number the nomenclature does not list) is `notListed`. */
export function useEnzymeDetail(ec: string, organism: string) {
  const query = useQuery({
    queryKey: ["enzymes", "detail", ec, organism],
    queryFn: () => apiJson<EnzymeDetail>(detailPath(ec, organism)),
    enabled: isCompleteEc(ec),
    staleTime: Infinity,
    retry: (count, error) => !(error instanceof ApiRequestError && error.kind === "server") && count < 2,
  });
  const notListed = query.error instanceof ApiRequestError && query.error.error.code === "not_found";
  return { ...query, notListed };
}

/**
 * The line under a candidate about the organism asked for: its proteins, or
 * the plain statement that the nomenclature records none. Null when no
 * organism was asked (there is then nothing to say).
 */
export function organismLine(
  proteins: { symbol: string }[],
  count: number,
  organismLabel: string | null,
  asked: boolean,
): string | null {
  if (!asked) return null;
  if (!organismLabel) return "The finder does not know this organism, so no proteins are listed.";
  if (count > 0) {
    if (proteins.length === 0) return `${organismLabel}: ${count} UniProt ${count === 1 ? "entry" : "entries"} in the nomenclature`;
    const shown = proteins.slice(0, 6).map((p) => p.symbol);
    const more = Math.max(count, proteins.length) - shown.length;
    return `${organismLabel}: ${shown.join(", ")}${more > 0 ? `, and ${more} more` : ""}`;
  }
  return `no ${organismLabel} protein recorded in the nomenclature; BRENDA may still hold measurements`;
}

/** What choosing a candidate sends: its EC, or its one successor when it was transferred; null when it cannot be chosen. */
export function chosenEc(c: Pick<EnzymeCandidate, "ec" | "status" | "superseded_by">): string | null {
  if (c.status === "active") return c.ec;
  if (c.status === "transferred" && c.superseded_by.length === 1) return c.superseded_by[0];
  return null;
}

/**
 * An enzyme as a form holds it: a complete EC number is the choice; any
 * other text (a name a link carried, an older run's request) only seeds the
 * finder's search and is never sent to the engine.
 */
export function subjectFields(value: string): { subject: string; subjectSeed: string } {
  const v = value.trim();
  return isCompleteEc(v) ? { subject: v, subjectSeed: "" } : { subject: "", subjectSeed: v };
}
