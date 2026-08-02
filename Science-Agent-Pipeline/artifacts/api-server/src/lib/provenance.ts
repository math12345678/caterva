/**
 * Per-parameter provenance: what is actually known about each value the
 * resolver returns. See ADR 0008 and Business/build-stages/STAGE_04_PART_03.md.
 */

export type ParameterOrigin = "resolved" | "user" | "default";

/**
 * Stage 5 Part 3: the citation-status contract, as distinct from the value
 * contract. A citation that supports a resolved value is either:
 *  - `verified` — exact organism and substrate match from a primary source
 *    (BRENDA exact tier);
 *  - `flagged` — cross-species or inferred (BRENDA cross-species tier).
 * There is no `rejected` on a resolved entry: a citation with no source, or
 * one that is LLM-generated with no corroborating record, cannot support a
 * `resolved` value at all — it manifests as origin `default` with a note.
 */
export type CitationStatus = "verified" | "flagged";

/**
 * Stage 5 Part 5: the deliberate narrowness. Only these parameters are
 * ever resolved from literature; everything else in the domain is a
 * teaching default, by decision, not by accident. Extending this list is
 * a new trust commitment: each entry needs a lookup path, a hand-verified
 * golden tuple, and contract tests (see STAGE_05_PART_05.md).
 */
export const RESOLVABLE_FIELDS: Record<string, string[]> = {
  mm: ["km"],
};

export interface ParameterProvenance {
  /** How this value was obtained for THIS query. */
  origin: ParameterOrigin;
  /** Only when `origin === "resolved"`: what looked the value up. */
  source?: string;
  /** Only when `origin === "resolved"`: the citation supporting THIS value. */
  citation?: string;
  /** Only when `origin === "resolved"`. */
  organism?: string;
  /** Only when `origin === "resolved"` (Stage 5 Part 3). */
  citationStatus?: CitationStatus;
  /** Why a lookup was attempted and failed, if so. */
  note?: string;
}

/**
 * Stage 5 Part 1: a resolved citation is stricter than a modelCitations entry.
 * A `resolved` citation is attached to a NUMBER; it must let a human re-find
 * the exact source of that number. A citation with no locator cannot.
 */
export function isLocatableCitation(citation: string): boolean {
  if (/https?:\/\//.test(citation)) return true;
  const refMatch = citation.match(/\(ref ([^)]*)\)/);
  if (refMatch) {
    const id = refMatch[1]!.trim();
    return id !== "" && id !== "n/a";
  }
  return false;
}

/**
 * Rule 2's analogue for provenance: hard violations mean the response must
 * not be returned. Returns a list of human-readable violations (empty when
 * the provenance is structurally sound).
 *
 * Violations:
 *  - a key in `parameterProvenance` absent from `parameters`, or vice versa
 *  - `origin: "resolved"` with no `citation`
 *  - a `citation` on any entry whose origin is not `"resolved"`
 *  - a `resolved` citation that carries no locator (ref id or URL) — the
 *    strict format rule (Stage 5 Part 1)
 *  - a `resolved` entry with no `citationStatus`, or a `citationStatus` on
 *    an entry whose origin is not `"resolved"` (Stage 5 Part 3)
 */
export function validateParameterProvenance(
  parameters: Record<string, unknown>,
  parameterProvenance: Record<string, ParameterProvenance>,
): string[] {
  const violations: string[] = [];
  const paramKeys = new Set(Object.keys(parameters));
  const provKeys = new Set(Object.keys(parameterProvenance));

  for (const key of provKeys) {
    if (!paramKeys.has(key)) {
      violations.push(`${key} has provenance but no parameter value`);
    }
  }
  for (const key of paramKeys) {
    if (!provKeys.has(key)) {
      violations.push(`${key} has a parameter value but no provenance`);
    }
  }

  for (const [key, prov] of Object.entries(parameterProvenance)) {
    if (prov.origin === "resolved" && !prov.citation) {
      violations.push(`${key} is marked resolved but carries no citation`);
    }
    if (prov.origin !== "resolved" && prov.citation !== undefined) {
      violations.push(`${key} has a citation but origin is '${prov.origin}'`);
    }
    if (prov.origin === "resolved" && prov.citation && !isLocatableCitation(prov.citation)) {
      violations.push(
        `${key} is marked resolved but its citation carries no locator (ref id or URL)`,
      );
    }
    if (prov.origin === "resolved" && prov.citation && prov.citationStatus === undefined) {
      violations.push(`${key} is marked resolved but carries no citation status`);
    }
    if (prov.origin !== "resolved" && prov.citationStatus !== undefined) {
      violations.push(`${key} has a citation status but origin is '${prov.origin}'`);
    }
  }

  return violations;
}

/** True when every parameter entry has origin "default". */
export function isAllDefaults(
  parameterProvenance: Record<string, ParameterProvenance>,
): boolean {
  return (
    Object.keys(parameterProvenance).length > 0 &&
    Object.values(parameterProvenance).every((p) => p.origin === "default")
  );
}
