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
 * offending branch never executed.
 *
 * (Corrected 2026-11-01: that sentence is as of 2026-08-09 and no longer
 * describes anything live. requirements.txt pinned stdpopsim only from
 * 2026-08-04 (0fba0c1) to 2026-08-16 (b1bc8f4, ADR 0061), when it left the
 * default install. popgen_resolver's last caller, the API server's
 * science_agent_runner.py, was removed on 2026-10-31 (ADR 0180), and the
 * resolver moved to archive/legacy_domains/ on 2026-11-01; v0.6.0 is the
 * last release that ships it.)
 *
 * (Note, 2026-11-01: this file was popgenProvenance.test.ts. Population
 * genetics and epidemiology were archived on 2026-09-27, after v0.4.0
 * (the last release that runs them), and no live domain can resolve
 * `mutation_rate` or `beta` any more, so the three cases built on those
 * keys were dropped and the file renamed for what it still holds: the km
 * half of the rule, which is the half ADR 0010 depends on, and one
 * non-governed key so the other half of ADR 0021 stays tested. Before the
 * rename it had 5 tests; it now has 3.)
 */
import { describe, expect, it } from "vitest";

import {
  buildResolvedKineticProvenance,
  validateParameterProvenance,
} from "../lib/provenance";

describe("ADR 0021 — STRENDA applies only to STRENDA-governed parameters", () => {
  it("a resolved key outside STRENDA_GOVERNED_FIELDS carries no strendaStatus", () => {
    // The generic half of ADR 0021, on a live key. `k` (the Gillespie rate
    // constant) is not one of km/vmax/kcat/ki, so the helper must not stamp
    // a STRENDA status on it, must not downgrade its citation for missing
    // assay conditions, and the entry it builds must pass the validator it
    // is then run through -- the assertion that would have caught the
    // original crash. The citation here is a test fixture, not a source.
    const prov = buildResolvedKineticProvenance({
      parameterKey: "k",
      source: "PubMed",
      citation: "Fixture et al. (ref 12345)",
      citationStatus: "verified",
      citationLocators: [
        {
          kind: "pubmed",
          value: "12345",
          deepLink: "https://pubmed.ncbi.nlm.nih.gov/12345/",
        },
      ],
    });

    expect(prov.origin).toBe("resolved");
    expect(prov.citationStatus).toBe("verified");
    expect(prov.strendaStatus).toBeUndefined();
    expect(prov.note).toBeUndefined();
    expect(validateParameterProvenance({ k: 0.5 }, { k: prov })).toEqual([]);
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
      citationLocators: [{ kind: "brenda_ref", value: "740253" }],
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
      citationLocators: [{ kind: "brenda_ref", value: "740253" }],
    });

    expect(prov.strendaStatus).toBe("complete");
    expect(prov.citationStatus).toBe("verified");
    expect(validateParameterProvenance({ km: 2.5 }, { km: prov })).toEqual([]);
  });
});
