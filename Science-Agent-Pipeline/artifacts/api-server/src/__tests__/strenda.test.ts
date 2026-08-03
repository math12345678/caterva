/**
 * STRENDA reporting requirement for resolved kinetic constants.
 *
 * The standard, verbatim:
 *
 *   "The temperature, pH and pressure (if other than atmospheric) of the
 *    assay MUST always be included, even if previously published."
 *   — STRENDA Guidelines v1.4.0, Beilstein-Institut,
 *     https://www.beilstein-strenda-db.org/strenda/public/guidelines.xhtml
 *
 * Km is not a property of an enzyme. It is a property of an enzyme measured
 * under conditions, and it moves with pH and temperature — so a Km reported
 * without them cannot be reproduced or compared against another lab's value.
 *
 * BRENDA stores pH optimum, temperature optimum and an experimental-conditions
 * commentary alongside every Km entry (Schomburg et al., Nucleic Acids
 * Research), so these fields exist upstream. Before this change Terrium
 * discarded them and still reported the value as `verified`.
 */

import { describe, expect, it } from "vitest";
import {
  buildResolvedKineticProvenance,
  missingStrendaFields,
  strendaStatusFor,
  validateParameterProvenance,
  STRENDA_GOVERNED_FIELDS,
  type AssayConditions,
  type ParameterProvenance,
} from "../lib/provenance";

const FULL: AssayConditions = {
  ph: 7.4,
  temperatureC: 25,
  buffer: "50 mM phosphate",
};
const CITATION = "BRENDA EC 1.1.1.27 (ref 12345)";

describe("strendaStatusFor", () => {
  it("is complete when pH and temperature are both present", () => {
    expect(strendaStatusFor(FULL)).toBe("complete");
    expect(strendaStatusFor({ ph: 7.4, temperatureC: 25 })).toBe("complete");
  });

  it("is incomplete when either mandatory field is missing", () => {
    expect(strendaStatusFor({ ph: 7.4 })).toBe("incomplete");
    expect(strendaStatusFor({ temperatureC: 25 })).toBe("incomplete");
    expect(strendaStatusFor({})).toBe("incomplete");
    expect(strendaStatusFor(undefined)).toBe("incomplete");
  });

  it("treats buffer as useful but not mandatory", () => {
    // STRENDA mandates temperature, pH and (non-atmospheric) pressure.
    // Buffer is materially useful and deliberately not required.
    expect(strendaStatusFor({ ph: 7.4, temperatureC: 25 })).toBe("complete");
  });

  it("accepts pH 0 and 0 degrees C", () => {
    // Both are real values. A truthiness check would reject them, which is
    // why the implementation tests presence and finiteness instead.
    expect(strendaStatusFor({ ph: 0, temperatureC: 0 })).toBe("complete");
  });

  it("rejects NaN and Infinity", () => {
    expect(strendaStatusFor({ ph: Number.NaN, temperatureC: 25 })).toBe(
      "incomplete",
    );
    expect(
      strendaStatusFor({ ph: 7, temperatureC: Number.POSITIVE_INFINITY }),
    ).toBe("incomplete");
  });
});

describe("missingStrendaFields", () => {
  it("names exactly what is absent", () => {
    expect(missingStrendaFields(FULL)).toEqual([]);
    expect(missingStrendaFields({ ph: 7.4 })).toEqual(["temperature"]);
    expect(missingStrendaFields({ temperatureC: 25 })).toEqual(["pH"]);
    expect(missingStrendaFields(undefined)).toEqual(["pH", "temperature"]);
  });
});

describe("buildResolvedKineticProvenance", () => {
  it("keeps verified when conditions are complete", () => {
    const p = buildResolvedKineticProvenance({
      source: "BRENDA",
      citation: CITATION,
      organism: "Homo sapiens",
      citationStatus: "verified",
      assayConditions: FULL,
    });
    expect(p.citationStatus).toBe("verified");
    expect(p.strendaStatus).toBe("complete");
    expect(p.note).toBeUndefined();
  });

  it("degrades verified to flagged when conditions are incomplete", () => {
    // The load-bearing behaviour. The value may be correct; it is not
    // independently reproducible, and "verified" in this codebase means a
    // human can go and check it.
    const p = buildResolvedKineticProvenance({
      source: "BRENDA",
      citation: CITATION,
      citationStatus: "verified",
      assayConditions: { ph: 7.4 },
    });
    expect(p.citationStatus).toBe("flagged");
    expect(p.strendaStatus).toBe("incomplete");
    expect(p.note).toContain("temperature");
    expect(p.note).toContain("STRENDA");
  });

  it("degrades when no conditions are supplied at all", () => {
    const p = buildResolvedKineticProvenance({
      source: "BRENDA",
      citation: CITATION,
      citationStatus: "verified",
    });
    expect(p.citationStatus).toBe("flagged");
    expect(p.strendaStatus).toBe("incomplete");
  });

  it("never upgrades flagged to verified", () => {
    // A cross-species match with perfect assay conditions is still
    // cross-species. Completeness cannot buy a tier.
    const p = buildResolvedKineticProvenance({
      source: "BRENDA cross-species",
      citation: CITATION,
      citationStatus: "flagged",
      assayConditions: FULL,
    });
    expect(p.citationStatus).toBe("flagged");
    expect(p.strendaStatus).toBe("complete");
  });

  it("preserves a caller-supplied note alongside the STRENDA note", () => {
    const p = buildResolvedKineticProvenance({
      source: "BRENDA",
      citation: CITATION,
      citationStatus: "verified",
      assayConditions: {},
      note: "Cross-species fallback from Rattus norvegicus.",
    });
    expect(p.note).toContain("Rattus norvegicus");
    expect(p.note).toContain("STRENDA");
  });

  it("omits optional keys rather than emitting undefined", () => {
    const p = buildResolvedKineticProvenance({
      source: "BRENDA",
      citation: CITATION,
      citationStatus: "flagged",
      assayConditions: FULL,
    });
    expect("organism" in p).toBe(false);
  });
});

describe("validateParameterProvenance — STRENDA rules", () => {
  const params = { km: 0.12 };

  it("accepts a complete resolved kinetic constant", () => {
    const prov: Record<string, ParameterProvenance> = {
      km: buildResolvedKineticProvenance({
        source: "BRENDA",
        citation: CITATION,
        citationStatus: "verified",
        assayConditions: FULL,
      }),
    };
    expect(validateParameterProvenance(params, prov)).toEqual([]);
  });

  it("rejects a resolved kinetic constant with no STRENDA status", () => {
    const prov: Record<string, ParameterProvenance> = {
      km: {
        origin: "resolved",
        source: "BRENDA",
        citation: CITATION,
        citationStatus: "flagged",
      },
    };
    const v = validateParameterProvenance(params, prov);
    expect(v.join(" ")).toContain("no STRENDA status");
  });

  it("rejects verified with incomplete conditions — the core rule", () => {
    const prov: Record<string, ParameterProvenance> = {
      km: {
        origin: "resolved",
        source: "BRENDA",
        citation: CITATION,
        citationStatus: "verified",
        assayConditions: { ph: 7.4 },
        strendaStatus: "incomplete",
      },
    };
    const v = validateParameterProvenance(params, prov);
    expect(v.join(" ")).toContain("not independently reproducible");
    expect(v.join(" ")).toContain("temperature");
  });

  it("rejects a STRENDA status that contradicts its own conditions", () => {
    const prov: Record<string, ParameterProvenance> = {
      km: {
        origin: "resolved",
        source: "BRENDA",
        citation: CITATION,
        citationStatus: "flagged",
        assayConditions: {},
        strendaStatus: "complete", // lying
      },
    };
    const v = validateParameterProvenance(params, prov);
    expect(v.join(" ")).toContain("claims STRENDA status 'complete'");
  });

  it("rejects assay conditions on a non-resolved parameter", () => {
    const v = validateParameterProvenance(
      { generations: 100 },
      { generations: { origin: "default", assayConditions: FULL } },
    );
    expect(v.join(" ")).toContain(
      "carries assay conditions but origin is 'default'",
    );
  });

  it("rejects a STRENDA status on a non-kinetic parameter", () => {
    const v = validateParameterProvenance(
      { generations: 100 },
      { generations: { origin: "default", strendaStatus: "complete" } },
    );
    expect(v.join(" ")).toContain("not a resolved kinetic constant");
  });

  it("does not impose STRENDA on non-kinetic resolved parameters", () => {
    // The requirement is about enzyme kinetic constants, not every number.
    const v = validateParameterProvenance(
      { s0: 10 },
      {
        s0: {
          origin: "resolved",
          source: "BRENDA",
          citation: CITATION,
          citationStatus: "verified",
        },
      },
    );
    expect(v).toEqual([]);
  });
});

describe("STRENDA_GOVERNED_FIELDS", () => {
  it("covers the kinetic constants the standard applies to", () => {
    for (const f of ["km", "vmax", "kcat", "ki"]) {
      expect(STRENDA_GOVERNED_FIELDS.has(f)).toBe(true);
    }
  });

  it("states the rule, not the current implementation", () => {
    // The set was written ahead of the implementation so that adding a
    // lookup path could not silently bypass the reporting requirement.
    //
    // That has now been exercised for real: `kcat` gained a lookup path in
    // Stage 8 (parse_brenda_turnover_html) and the STRENDA rule applied to
    // it automatically, with no change to this set. `vmax` still has none --
    // it is derived from kcat and [E]0 rather than resolved (ADR 0013), and
    // [E]0 is a property of an experiment, not of an enzyme.
    expect(STRENDA_GOVERNED_FIELDS.has("vmax")).toBe(true);
    expect(STRENDA_GOVERNED_FIELDS.has("kcat")).toBe(true);
    expect(STRENDA_GOVERNED_FIELDS.has("generations")).toBe(false);
  });
});
