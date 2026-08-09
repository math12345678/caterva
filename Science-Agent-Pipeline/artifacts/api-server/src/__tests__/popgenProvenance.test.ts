/**
 * Regression tests for ADR 0021: buildResolvedKineticProvenance must apply
 * the STRENDA rule ONLY to parameters STRENDA actually governs.
 *
 * The bug: the helper unconditionally computed a `strendaStatus` and
 * stamped it onto every entry it built. `validateParameterProvenance`
 * treats a `strendaStatus` on a field outside `STRENDA_GOVERNED_FIELDS` as
 * a hard violation, and `provenanceViolations` throws on any violation --
 * so a successfully-resolved `mutation_rate` crashed `resolveQuery()` with
 * "Internal error: invalid parameter provenance" instead of returning a
 * perfectly good literature-backed value. Before reaching that throw it had
 * also silently downgraded the citation verified -> flagged and attached a
 * note about unreported assay pH to a per-generation substitution rate,
 * which has no assay pH.
 *
 * It never surfaced in CI because `stdpopsim` is not installed in the test
 * sandbox, so `popgen_resolver` always returns found=false and the
 * offending branch never executed. It would fire on any machine with
 * stdpopsim present -- i.e. in real use.
 */
import { describe, expect, it } from "vitest";

import {
  buildResolvedKineticProvenance,
  validateParameterProvenance,
} from "../lib/provenance";

describe("ADR 0021 — STRENDA applies only to STRENDA-governed parameters", () => {
  it("a resolved mutation_rate carries no strendaStatus and stays verified", () => {
    const prov = buildResolvedKineticProvenance({
      parameterKey: "mutation_rate",
      source: "stdpopsim",
      citation: "Rahbari et al. (ref 12345)",
      organism: "Homo sapiens",
      citationStatus: "verified",
    });

    expect(prov.origin).toBe("resolved");
    // Not downgraded: a mutation rate has no assay pH to be missing.
    expect(prov.citationStatus).toBe("verified");
    expect(prov.strendaStatus).toBeUndefined();
    // And no nonsensical "assay pH not reported" note.
    expect(prov.note).toBeUndefined();
  });

  it("a resolved mutation_rate produces NO provenance violations", () => {
    // The assertion that would have caught the crash: the entry the
    // resolver builds must survive the validator the resolver then runs it
    // through.
    const prov = buildResolvedKineticProvenance({
      parameterKey: "mutation_rate",
      source: "stdpopsim",
      citation: "Rahbari et al. (ref 12345)",
      organism: "Homo sapiens",
      citationStatus: "verified",
    });

    const violations = validateParameterProvenance(
      { mutation_rate: 1.29e-8 },
      { mutation_rate: prov },
    );
    expect(violations).toEqual([]);
  });

  it("beta/gamma (epidemiology) likewise carry no strendaStatus", () => {
    const prov = buildResolvedKineticProvenance({
      parameterKey: "beta",
      source: "PubMed",
      citation: "Hussein et al. (ref 33214421)",
      citationStatus: "verified",
      note: "beta = R0 * gamma",
    });

    expect(prov.citationStatus).toBe("verified");
    expect(prov.strendaStatus).toBeUndefined();
    expect(prov.note).toBe("beta = R0 * gamma");
    expect(validateParameterProvenance({ beta: 0.576 }, { beta: prov })).toEqual(
      [],
    );
  });

  it("km IS still STRENDA-governed and still degrades without conditions", () => {
    // The fix must not weaken the rule where it genuinely applies -- this
    // is the half of the behaviour ADR 0010 depends on.
    const prov = buildResolvedKineticProvenance({
      parameterKey: "km",
      source: "brenda_exact",
      citation: "BRENDA (ref 740253)",
      organism: "Homo sapiens",
      citationStatus: "verified",
    });

    expect(prov.strendaStatus).toBe("incomplete");
    expect(prov.citationStatus).toBe("flagged");
    expect(prov.note).toMatch(/STRENDA/);
  });

  it("km with complete assay conditions stays verified", () => {
    const prov = buildResolvedKineticProvenance({
      parameterKey: "km",
      source: "brenda_exact",
      citation: "BRENDA (ref 740253)",
      organism: "Homo sapiens",
      citationStatus: "verified",
      assayConditions: { ph: 7.4, temperatureC: 37 },
    });

    expect(prov.strendaStatus).toBe("complete");
    expect(prov.citationStatus).toBe("verified");
    expect(validateParameterProvenance({ km: 2.5 }, { km: prov })).toEqual([]);
  });
});
