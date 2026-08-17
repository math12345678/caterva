import { describe, expect, it } from "vitest";

import {
  assessCoherence,
  sourceIdentity,
  type ParameterUnderTest,
} from "../lib/assayCoherence";

/**
 * The scenario under test is the one Lisa Jeske described: a Km from one
 * paper and a Ki from another, combined into a single competitive-inhibition
 * model. Every individual value is real, cited and fully described. The
 * model is still of no experiment that was ever run.
 *
 * Values below are shaped like real BRENDA rows for lactate dehydrogenase
 * (EC 1.1.1.27) but are fixtures, not claims about the literature.
 */

const KM_AT_74_25: ParameterUnderTest = {
  key: "km",
  conditions: { ph: 7.4, temperatureC: 25 },
  citationLocators: [{ kind: "brenda_ref", value: "740253" }],
};

const KI_AT_60_37: ParameterUnderTest = {
  key: "ki",
  conditions: { ph: 6.0, temperatureC: 37 },
  citationLocators: [{ kind: "brenda_ref", value: "711801" }],
};

const KI_AT_74_25_OTHER_PAPER: ParameterUnderTest = {
  key: "ki",
  conditions: { ph: 7.4, temperatureC: 25 },
  citationLocators: [{ kind: "brenda_ref", value: "711801" }],
};

const KI_SAME_PAPER_AS_KM: ParameterUnderTest = {
  key: "ki",
  conditions: { ph: 7.4, temperatureC: 25 },
  citationLocators: [{ kind: "brenda_ref", value: "740253" }],
};

describe("assay coherence — the failure per-parameter scoring cannot see", () => {
  it("reports differing conditions when two papers disagree", () => {
    const report = assessCoherence([KM_AT_74_25, KI_AT_60_37]);
    expect(report.verdict).toBe("differing_conditions");
    expect(report.spread?.phRange?.delta).toBeCloseTo(1.4, 5);
    expect(report.spread?.temperatureRangeC?.delta).toBeCloseTo(12, 5);
  });

  it("states plainly that the values were never jointly measured", () => {
    // The numbers alone do not tell a student anything. The sentence is the
    // deliverable, so it is the thing asserted on.
    const report = assessCoherence([KM_AT_74_25, KI_AT_60_37]);
    expect(report.reason).toMatch(/never true of the same enzyme/i);
    expect(report.reason).toContain("7.4");
    expect(report.reason).toContain("6");
    expect(report.reason).toContain("37");
  });

  it("refuses to say whether the divergence matters", () => {
    // Terrium does not know this enzyme's pH sensitivity. Claiming the
    // model is invalid would be as unsourced as claiming it is fine.
    const report = assessCoherence([KM_AT_74_25, KI_AT_60_37]);
    expect(report.reason).toMatch(/does not know and does not guess/i);
  });

  it("recognises two papers that used the same conditions", () => {
    const report = assessCoherence([KM_AT_74_25, KI_AT_74_25_OTHER_PAPER]);
    expect(report.verdict).toBe("same_conditions");
    expect(report.spread?.phRange?.delta).toBe(0);
  });

  it("does not overclaim for same_conditions — buffer is not compared", () => {
    const report = assessCoherence([KM_AT_74_25, KI_AT_74_25_OTHER_PAPER]);
    // Jeske named cofactors and buffers alongside pH and temperature.
    // Only two of the four are checked, and the verdict must say so.
    expect(report.reason).toMatch(/buffer/i);
    expect(report.reason).toMatch(/may still differ/i);
  });

  it("recognises the strongest case: one paper reporting both", () => {
    const report = assessCoherence([KM_AT_74_25, KI_SAME_PAPER_AS_KM]);
    expect(report.verdict).toBe("same_source");
    expect(report.reason).toContain("740253");
  });
});

describe("source identity cannot be faked by an enzyme id", () => {
  it("ignores brenda_ec, which names the enzyme and not the paper", () => {
    // Every LDH parameter shares EC 1.1.1.27. If that counted as source
    // identity, every LDH model on earth would report same_source -- the
    // most reassuring possible wrong answer.
    const km: ParameterUnderTest = {
      key: "km",
      conditions: { ph: 7.4, temperatureC: 25 },
      citationLocators: [{ kind: "brenda_ec", value: "1.1.1.27" }],
    };
    const ki: ParameterUnderTest = {
      key: "ki",
      conditions: { ph: 6.0, temperatureC: 37 },
      citationLocators: [{ kind: "brenda_ec", value: "1.1.1.27" }],
    };
    expect(sourceIdentity(km.citationLocators)).toBeUndefined();
    expect(assessCoherence([km, ki]).verdict).toBe("differing_conditions");
  });

  it("keeps namespaces apart — PMID 740253 is not BRENDA ref 740253", () => {
    const km: ParameterUnderTest = {
      key: "km",
      conditions: { ph: 7.4, temperatureC: 25 },
      citationLocators: [{ kind: "pubmed", value: "740253" }],
    };
    const ki: ParameterUnderTest = {
      key: "ki",
      conditions: { ph: 7.4, temperatureC: 25 },
      citationLocators: [{ kind: "brenda_ref", value: "740253" }],
    };
    expect(sourceIdentity(km.citationLocators)).not.toBe(
      sourceIdentity(ki.citationLocators),
    );
    // Identical conditions, genuinely different namespaces -> not one paper.
    expect(assessCoherence([km, ki]).verdict).toBe("same_conditions");
  });

  it("does not claim same_source when one parameter has no identifier", () => {
    const km: ParameterUnderTest = {
      key: "km",
      conditions: { ph: 7.4, temperatureC: 25 },
      citationLocators: [{ kind: "brenda_ref", value: "740253" }],
    };
    const ki: ParameterUnderTest = {
      key: "ki",
      conditions: { ph: 7.4, temperatureC: 25 },
      citationLocators: [],
    };
    expect(assessCoherence([km, ki]).verdict).not.toBe("same_source");
  });
});

describe("unassessable never masquerades as a pass", () => {
  it("is unassessable when neither parameter reports conditions", () => {
    const bare = (key: string): ParameterUnderTest => ({
      key,
      conditions: undefined,
      citationLocators: [{ kind: "brenda_ref", value: key }],
    });
    const report = assessCoherence([bare("km"), bare("ki")]);
    expect(report.verdict).toBe("unassessable");
  });

  it("says outright that unassessed is not the same as sound", () => {
    // The one sentence that stops a reader treating silence as approval.
    const bare = (key: string): ParameterUnderTest => ({
      key,
      citationLocators: [{ kind: "brenda_ref", value: key }],
    });
    const report = assessCoherence([bare("km"), bare("ki")]);
    expect(report.reason).toMatch(/NOT a finding that the model is sound/);
  });

  it("names which parameters were dropped and why", () => {
    const report = assessCoherence([
      KM_AT_74_25,
      { key: "ki", citationLocators: [{ kind: "brenda_ref", value: "711801" }] },
    ]);
    expect(report.verdict).toBe("unassessable");
    expect(report.excluded.map((e) => e.key)).toContain("ki");
    expect(report.excluded[0].why).toMatch(/neither pH nor temperature/);
  });

  it("is unassessable, not coherent, for a single-parameter model", () => {
    // `mm` resolves only km. There is no pair, and the honest verdict is
    // that the question does not apply -- not that the model passed.
    const report = assessCoherence([KM_AT_74_25]);
    expect(report.verdict).toBe("unassessable");
    expect(report.reason).toMatch(/no pair to be incoherent/i);
  });
});

describe("a partially-reported pair is still compared on what it has", () => {
  it("compares temperature when only one parameter reports pH", () => {
    const km: ParameterUnderTest = {
      key: "km",
      conditions: { ph: 7.4, temperatureC: 25 },
      citationLocators: [{ kind: "brenda_ref", value: "A" }],
    };
    const ki: ParameterUnderTest = {
      key: "ki",
      conditions: { temperatureC: 37 },
      citationLocators: [{ kind: "brenda_ref", value: "B" }],
    };
    const report = assessCoherence([km, ki]);
    expect(report.verdict).toBe("differing_conditions");
    expect(report.spread?.temperatureRangeC?.delta).toBeCloseTo(12, 5);
    // Only one pH value exists, so there is no pH range to report. An
    // absent range must not be reported as a range of zero -- that would
    // assert agreement nobody measured.
    expect(report.spread?.phRange).toBeUndefined();
  });
});

describe("a caller-supplied tolerance annotates but never decides", () => {
  const TOL = {
    phTolerance: 0.2,
    temperatureToleranceC: 5,
    basis: "test fixture, not a scientific claim",
  };

  it("does not change the verdict when the spread is within tolerance", () => {
    const km: ParameterUnderTest = {
      key: "km",
      conditions: { ph: 7.4, temperatureC: 25 },
      citationLocators: [{ kind: "brenda_ref", value: "A" }],
    };
    const ki: ParameterUnderTest = {
      key: "ki",
      conditions: { ph: 7.5, temperatureC: 27 },
      citationLocators: [{ kind: "brenda_ref", value: "B" }],
    };
    const withTol = assessCoherence([km, ki], TOL);
    const without = assessCoherence([km, ki]);

    // Same fact, whether or not anyone stated a tolerance. The tolerance is
    // an opinion; the verdict is an observation.
    expect(withTol.verdict).toBe(without.verdict);
    expect(withTol.verdict).toBe("differing_conditions");
    expect(withTol.toleranceAssessment).toMatch(/within the tolerance/i);
  });

  it("reports exceedance without escalating the verdict", () => {
    const report = assessCoherence([KM_AT_74_25, KI_AT_60_37], TOL);
    expect(report.verdict).toBe("differing_conditions");
    expect(report.toleranceAssessment).toMatch(/exceeds the stated/);
    expect(report.toleranceAssessment).toContain(TOL.basis);
  });

  it("omits the assessment entirely when no tolerance was supplied", () => {
    const report = assessCoherence([KM_AT_74_25, KI_AT_60_37]);
    expect(report.toleranceAssessment).toBeUndefined();
  });
});

/**
 * Buffer comparison (ADR 0028) — the third of the four things Jeske named.
 *
 * The identity resolution lives in Python; this asserts what the TypeScript
 * side does with it. Two properties matter more than the verdicts:
 *
 *   1. Buffer NEVER changes the pH/temperature verdict. They answer
 *      different questions, and the most common honest answer to the buffer
 *      question is "the sources did not say" — which must not be allowed to
 *      degrade a temperature finding that WAS established.
 *   2. Nothing falls back to string equality. `"0.5 M Tris-HCl buffer"` and
 *      `"Tris-HCl"` are the same buffer, and a fallback that gets the
 *      common case wrong is worse than no fallback.
 */

const TRIS_ID = {
  raw: "0.5 M Tris-HCl buffer",
  species: "Tris-HCl",
  cid: 93573,
  parent_cid: 6503,
  concentration_text: "0.5 M",
  status: "resolved",
};
const TRIS_FREE_BASE_ID = {
  raw: "Tris",
  species: "Tris",
  cid: 6503,
  parent_cid: 6503,
  concentration_text: null,
  status: "resolved",
};
const PHOSPHATE_ID = {
  raw: "phosphate",
  species: "phosphate",
  cid: 1061,
  parent_cid: 1061,
  concentration_text: null,
  status: "resolved",
};

function withBuffer(
  key: string,
  ph: number,
  temperatureC: number,
  ref: string,
  bufferIdentity?: unknown,
  buffer?: string,
): ParameterUnderTest {
  return {
    key,
    conditions: {
      ph,
      temperatureC,
      ...(buffer ? { buffer } : {}),
      ...(bufferIdentity ? { bufferIdentity: bufferIdentity as never } : {}),
    },
    citationLocators: [{ kind: "brenda_ref", value: ref }],
  };
}

describe("buffer comparison", () => {
  it("calls a salt and its free base the same buffer", () => {
    // The whole reason identity is compared at the PubChem PARENT. Comparing
    // raw strings, or bare CIDs, would report a difference here.
    const report = assessCoherence([
      withBuffer("km", 7.4, 25, "A", TRIS_ID, "0.5 M Tris-HCl buffer"),
      withBuffer("ki", 7.4, 25, "B", TRIS_FREE_BASE_ID, "Tris"),
    ]);
    expect(report.buffer?.verdict).toBe("same");
    expect(report.buffer?.reason).toContain("6503");
  });

  it("admits it ignored concentration when it says same", () => {
    const report = assessCoherence([
      withBuffer("km", 7.4, 25, "A", TRIS_ID, "0.5 M Tris-HCl buffer"),
      withBuffer("ki", 7.4, 25, "B", TRIS_FREE_BASE_ID, "Tris"),
    ]);
    expect(report.buffer?.reason).toMatch(/concentration was not compared/i);
    expect(report.buffer?.reason).toContain("0.5 M");
  });

  it("reports genuinely different buffers, naming both", () => {
    const report = assessCoherence([
      withBuffer("km", 7.4, 25, "A", TRIS_ID, "0.5 M Tris-HCl buffer"),
      withBuffer("ki", 7.4, 25, "B", PHOSPHATE_ID, "phosphate"),
    ]);
    expect(report.buffer?.verdict).toBe("different");
    expect(report.buffer?.reason).toContain("phosphate");
    expect(report.buffer?.reason).toContain("Tris");
  });

  it("does not let a buffer difference change the conditions verdict", () => {
    // Identical pH and temperature, different buffers. `same_conditions` is
    // still the right answer to the question it asks; the buffer finding
    // rides alongside. Folding them would degrade an established fact
    // because a different fact disagreed.
    const report = assessCoherence([
      withBuffer("km", 7.4, 25, "A", TRIS_ID, "0.5 M Tris-HCl buffer"),
      withBuffer("ki", 7.4, 25, "B", PHOSPHATE_ID, "phosphate"),
    ]);
    expect(report.verdict).toBe("same_conditions");
    expect(report.buffer?.verdict).toBe("different");
  });

  it("does not let a missing buffer change the conditions verdict", () => {
    // The most common case by far, and the one where folding would do the
    // most damage: an unreported buffer would silently downgrade every
    // temperature finding in the corpus.
    const report = assessCoherence([
      withBuffer("km", 7.4, 25, "A"),
      withBuffer("ki", 6.0, 37, "B"),
    ]);
    expect(report.verdict).toBe("differing_conditions");
    expect(report.buffer?.verdict).toBe("not_reported");
  });

  it("treats an unreported buffer as unknown, never as agreement", () => {
    const report = assessCoherence([
      withBuffer("km", 7.4, 25, "A", TRIS_ID, "0.5 M Tris-HCl buffer"),
      withBuffer("ki", 7.4, 25, "B"),
    ]);
    expect(report.buffer?.verdict).toBe("not_reported");
    expect(report.buffer?.verdict).not.toBe("same");
    expect(report.buffer?.reason).toMatch(/not evidence the buffers agree/i);
  });

  it("treats an unresolvable buffer as unknown, never as agreement", () => {
    const report = assessCoherence([
      withBuffer("km", 7.4, 25, "A", TRIS_ID, "0.5 M Tris-HCl buffer"),
      withBuffer("ki", 7.4, 25, "B", {
        raw: "house buffer B",
        species: "house buffer B",
        status: "unresolvable",
        reason: "PubChem holds no compound named 'house buffer B'.",
      }, "house buffer B"),
    ]);
    expect(report.buffer?.verdict).toBe("unknown");
    expect(report.buffer?.reason).toContain("house buffer B");
  });

  it("never falls back to string equality", () => {
    // Identical raw strings, no identities. A string fallback would say
    // `same`; there is no fallback, so it says the sources did not resolve.
    const report = assessCoherence([
      withBuffer("km", 7.4, 25, "A", undefined, "Tris-HCl"),
      withBuffer("ki", 7.4, 25, "B", undefined, "Tris-HCl"),
    ]);
    expect(report.buffer?.verdict).not.toBe("same");
  });

  it("reports the raw strings so the resolution can be argued with", () => {
    const report = assessCoherence([
      withBuffer("km", 7.4, 25, "A", TRIS_ID, "0.5 M Tris-HCl buffer"),
      withBuffer("ki", 7.4, 25, "B", PHOSPHATE_ID, "phosphate"),
    ]);
    expect(report.buffer?.reported["km"]).toBe("0.5 M Tris-HCl buffer");
    expect(report.buffer?.reported["ki"]).toBe("phosphate");
  });
});

/**
 * Effector comparison (ADR 0032) — the fourth and last of the things Jeske
 * named, reaching the API response.
 *
 * Extraction and PubChem resolution happen in Python. What is asserted here
 * is the TypeScript half: that the presence flag survives, that it is part
 * of the comparison key, and that — as with buffers — an effector finding
 * never silently rewrites the pH/temperature verdict.
 */

const FBP_PRESENT = {
  raw: "in presence of fructose 1,6-bisphosphate",
  compound_text: "fructose 1,6-bisphosphate",
  presence: "present",
  concentration_text: null,
  identity: { raw: "fructose 1,6-bisphosphate", parent_cid: 172922, status: "resolved" },
};
const FBP_ABSENT = { ...FBP_PRESENT, raw: "in absence of fructose 1,6-bisphosphate", presence: "absent" };
// The same compound spelled the way the other papers spell it.
const FBP_OTHER_SPELLING = {
  raw: "presence of D-fructose-1,6-diphosphate",
  compound_text: "D-fructose-1,6-diphosphate",
  presence: "present",
  concentration_text: null,
  identity: { raw: "D-fructose-1,6-diphosphate", parent_cid: 172922, status: "resolved" },
};
const NADH_UNRESOLVED = {
  raw: "in the presence of house cofactor Q",
  compound_text: "house cofactor Q",
  presence: "present",
  concentration_text: null,
  identity: { raw: "house cofactor Q", status: "unresolvable", reason: "PubChem holds no compound named it." },
};

function withEffectors(
  key: string,
  ref: string,
  effs: unknown[],
): ParameterUnderTest {
  return {
    key,
    conditions: { ph: 6.0, temperatureC: 25, effectors: effs as never },
    citationLocators: [{ kind: "brenda_ref", value: ref }],
  };
}

describe("effector comparison", () => {
  it("calls presence and absence of one compound different", () => {
    // The pair ADR 0032 exists for. Same pH, same temperature, same paper's
    // conditions -- every other axis agrees.
    const report = assessCoherence([
      withEffectors("km", "A", [FBP_PRESENT]),
      withEffectors("ki", "B", [FBP_ABSENT]),
    ]);
    expect(report.effectors?.verdict).toBe("different");
    expect(report.effectors?.reason).toContain("PRESENCE");
    expect(report.effectors?.reason).toContain("ABSENCE");
  });

  it("says why it matters, not only that it differs", () => {
    const report = assessCoherence([
      withEffectors("km", "A", [FBP_PRESENT]),
      withEffectors("ki", "B", [FBP_ABSENT]),
    ]);
    expect(report.effectors?.reason).toMatch(/changes the kinetics/i);
  });

  it("treats two spellings of one compound as the same effector", () => {
    // Resolved at the PubChem parent, so the four corpus spellings collapse.
    const report = assessCoherence([
      withEffectors("km", "A", [FBP_PRESENT]),
      withEffectors("ki", "B", [FBP_OTHER_SPELLING]),
    ]);
    expect(report.effectors?.verdict).toBe("same");
  });

  it("does not let an effector difference change the conditions verdict", () => {
    // Identical pH and temperature. `same_conditions` is still the right
    // answer to the question it asks; the effector finding rides alongside.
    const report = assessCoherence([
      withEffectors("km", "A", [FBP_PRESENT]),
      withEffectors("ki", "B", [FBP_ABSENT]),
    ]);
    expect(report.verdict).toBe("same_conditions");
    expect(report.effectors?.verdict).toBe("different");
  });

  it("does not let a missing effector change the conditions verdict", () => {
    const report = assessCoherence([
      withEffectors("km", "A", []),
      withEffectors("ki", "B", []),
    ]);
    expect(report.verdict).toBe("same_conditions");
    expect(report.effectors?.verdict).toBe("not_reported");
  });

  it("treats an unreported effector as unknown, never as agreement", () => {
    const report = assessCoherence([
      withEffectors("km", "A", [FBP_PRESENT]),
      withEffectors("ki", "B", []),
    ]);
    expect(report.effectors?.verdict).not.toBe("same");
    expect(report.effectors?.reason).toMatch(/what was in the tube/i);
  });

  it("says nothing reported is a gap in the sources, not agreement", () => {
    const report = assessCoherence([
      withEffectors("km", "A", []),
      withEffectors("ki", "B", []),
    ]);
    expect(report.effectors?.verdict).toBe("not_reported");
    expect(report.effectors?.reason).toMatch(/not a finding that the\s+conditions agreed/i);
  });

  it("reports unknown when the names match but the compound did not resolve", () => {
    const report = assessCoherence([
      withEffectors("km", "A", [NADH_UNRESOLVED]),
      withEffectors("ki", "B", [NADH_UNRESOLVED]),
    ]);
    expect(report.effectors?.verdict).toBe("unknown");
    expect(report.effectors?.reason).toMatch(/Matching text is not matching chemistry/);
  });

  it("reports the raw clauses so the parse can be argued with", () => {
    const report = assessCoherence([
      withEffectors("km", "A", [FBP_PRESENT]),
      withEffectors("ki", "B", [FBP_ABSENT]),
    ]);
    expect(report.effectors?.reported["km"]).toEqual([FBP_PRESENT.raw]);
    expect(report.effectors?.reported["ki"]).toEqual([FBP_ABSENT.raw]);
  });
});
