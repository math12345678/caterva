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

/**
 * Assay conditions under which a kinetic constant was measured.
 *
 * This is not bookkeeping. The STRENDA Guidelines — the reporting standard
 * for enzymology data, registered in FAIRsharing and recommended by more than
 * 60 biochemistry journals — state the requirement without qualification:
 *
 *   "The temperature, pH and pressure (if other than atmospheric) of the
 *    assay MUST always be included, even if previously published."
 *   — STRENDA Guidelines v1.4.0, Beilstein-Institut
 *
 * The reason is physical, not clerical. Km is not a property of an enzyme; it
 * is a property of an enzyme measured under conditions. The same enzyme and
 * substrate yield different Km values at different pH and temperature, so a
 * Km reported without them cannot be reproduced and cannot be compared
 * against another laboratory's number.
 *
 * BRENDA — the source Terrium resolves from — stores pH optimum, temperature
 * optimum, and an experimental-conditions commentary alongside every Km
 * entry (Schomburg et al., Nucleic Acids Research). So these fields are
 * available upstream; omitting them discards data the source already
 * supplied.
 *
 * `pressure` is deliberately absent: STRENDA requires it only when other than
 * atmospheric, and no path in Terrium currently resolves a non-atmospheric
 * measurement. Adding it later is a field addition, not a contract change.
 */
export interface AssayConditions {
  /** Assay pH. STRENDA: mandatory. */
  ph?: number;
  /** Assay temperature in degrees Celsius. STRENDA: mandatory. */
  temperatureC?: number;
  /** Buffer system, when reported. Not STRENDA-mandatory but materially useful. */
  buffer?: string;
}

/**
 * Whether a resolved value meets STRENDA's minimum reporting requirement.
 *
 *  - `complete`   — pH and temperature both present.
 *  - `incomplete` — one or both missing. The value may still be correct; it
 *                   is not independently reproducible, which is what the
 *                   standard is about.
 *
 * There is deliberately no `not_applicable`: this status is only ever set on
 * parameters in `STRENDA_GOVERNED_FIELDS`, and for anything else the field is
 * simply absent.
 */
export type StrendaStatus = "complete" | "incomplete";

/**
 * Parameters that are enzyme kinetic constants, and therefore fall under
 * STRENDA's reporting requirement.
 *
 * Km is the only one Terrium currently resolves (see RESOLVABLE_FIELDS). vmax
 * and kcat are listed because they are governed by the same standard the
 * moment a lookup path exists for them — the list states the rule, not the
 * current implementation, so extending RESOLVABLE_FIELDS cannot silently
 * bypass the requirement.
 */
export const STRENDA_GOVERNED_FIELDS: ReadonlySet<string> = new Set([
  "km",
  "vmax",
  "kcat",
  "ki",
]);

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
  /**
   * Only when `origin === "resolved"` and the parameter is a kinetic constant.
   * The conditions the value was measured under (STRENDA).
   */
  assayConditions?: AssayConditions;
  /**
   * Only for STRENDA-governed resolved parameters: whether the assay
   * conditions meet the standard's minimum.
   */
  strendaStatus?: StrendaStatus;
  /** Why a lookup was attempted and failed, if so. */
  note?: string;
}

/**
 * STRENDA completeness for a single parameter.
 *
 * Both pH and temperature must be present and finite. A `null` pH is not the
 * same as pH 0 — 0 is a real (if extreme) value, so the check is on presence
 * and finiteness rather than truthiness, which would silently reject pH 0.
 */
export function strendaStatusFor(
  conditions: AssayConditions | undefined,
): StrendaStatus {
  if (!conditions) return "incomplete";
  const hasPh = typeof conditions.ph === "number" && Number.isFinite(conditions.ph);
  const hasTemp =
    typeof conditions.temperatureC === "number" &&
    Number.isFinite(conditions.temperatureC);
  return hasPh && hasTemp ? "complete" : "incomplete";
}

/** Which STRENDA-mandatory fields are missing, for a human-readable reason. */
export function missingStrendaFields(
  conditions: AssayConditions | undefined,
): string[] {
  const missing: string[] = [];
  if (!conditions || typeof conditions.ph !== "number" || !Number.isFinite(conditions.ph)) {
    missing.push("pH");
  }
  if (
    !conditions ||
    typeof conditions.temperatureC !== "number" ||
    !Number.isFinite(conditions.temperatureC)
  ) {
    missing.push("temperature");
  }
  return missing;
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

    // --- STRENDA reporting requirement ---------------------------------
    //
    // The rule that carries the weight: a kinetic constant whose assay
    // conditions are unknown cannot be called `verified`. It may well be the
    // right number, but "verified" in this codebase means a human can go and
    // check it, and a Km without pH and temperature cannot be re-measured or
    // compared. Degrading it to `flagged` keeps the value usable while
    // saying plainly what is missing -- the same shape as Rule 2's
    // impossible/implausible distinction, applied to reporting completeness
    // rather than to physics.
    const strendaGoverned =
      prov.origin === "resolved" && STRENDA_GOVERNED_FIELDS.has(key.toLowerCase());

    if (strendaGoverned) {
      const expected = strendaStatusFor(prov.assayConditions);
      if (prov.strendaStatus === undefined) {
        violations.push(
          `${key} is a resolved kinetic constant but carries no STRENDA status`,
        );
      } else if (prov.strendaStatus !== expected) {
        violations.push(
          `${key} claims STRENDA status '${prov.strendaStatus}' but its assay ` +
            `conditions are '${expected}' (missing: ` +
            `${missingStrendaFields(prov.assayConditions).join(", ") || "none"})`,
        );
      }
      if (prov.citationStatus === "verified" && expected === "incomplete") {
        violations.push(
          `${key} is marked citationStatus 'verified' but its assay conditions ` +
            `are incomplete (missing: ${missingStrendaFields(prov.assayConditions).join(", ")}). ` +
            `STRENDA requires temperature and pH for kinetic data; a value ` +
            `without them is not independently reproducible, so it must be ` +
            `'flagged' rather than 'verified'.`,
        );
      }
    }

    if (!strendaGoverned && prov.strendaStatus !== undefined) {
      violations.push(
        `${key} carries a STRENDA status but is not a resolved kinetic constant`,
      );
    }
    if (prov.origin !== "resolved" && prov.assayConditions !== undefined) {
      violations.push(
        `${key} carries assay conditions but origin is '${prov.origin}'`,
      );
    }
  }

  return violations;
}

/**
 * Build the provenance entry for a resolved kinetic constant, applying the
 * STRENDA rule in one place so no caller can forget it.
 *
 * Callers pass the citation tier they believe applies; this function may
 * degrade `verified` to `flagged` when the assay conditions are incomplete.
 * It never upgrades — a cross-species match with perfect conditions is still
 * cross-species.
 */
export function buildResolvedKineticProvenance(args: {
  source: string;
  citation: string;
  organism?: string;
  citationStatus: CitationStatus;
  assayConditions?: AssayConditions;
  note?: string;
}): ParameterProvenance {
  const strendaStatus = strendaStatusFor(args.assayConditions);
  const missing = missingStrendaFields(args.assayConditions);

  const citationStatus: CitationStatus =
    args.citationStatus === "verified" && strendaStatus === "incomplete"
      ? "flagged"
      : args.citationStatus;

  const notes: string[] = [];
  if (args.note) notes.push(args.note);
  if (strendaStatus === "incomplete") {
    notes.push(
      `Assay ${missing.join(" and ")} not reported by the source; ` +
        `STRENDA requires ${missing.length > 1 ? "them" : "it"} for kinetic data, ` +
        `so this value is flagged rather than verified.`,
    );
  }

  return {
    origin: "resolved",
    source: args.source,
    citation: args.citation,
    ...(args.organism !== undefined ? { organism: args.organism } : {}),
    citationStatus,
    ...(args.assayConditions !== undefined
      ? { assayConditions: args.assayConditions }
      : {}),
    strendaStatus,
    ...(notes.length > 0 ? { note: notes.join(" ") } : {}),
  };
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
