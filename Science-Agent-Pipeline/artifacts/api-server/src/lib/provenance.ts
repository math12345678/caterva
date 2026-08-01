/**
 * Per-parameter provenance: what is actually known about each value the
 * resolver returns. See ADR 0008 and Business/build-stages/STAGE_04_PART_03.md.
 */

export type ParameterOrigin = "resolved" | "user" | "default";

export interface ParameterProvenance {
  /** How this value was obtained for THIS query. */
  origin: ParameterOrigin;
  /** Only when `origin === "resolved"`: what looked the value up. */
  source?: string;
  /** Only when `origin === "resolved"`: the citation supporting THIS value. */
  citation?: string;
  /** Only when `origin === "resolved"`. */
  organism?: string;
  /** Why a lookup was attempted and failed, if so. */
  note?: string;
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
