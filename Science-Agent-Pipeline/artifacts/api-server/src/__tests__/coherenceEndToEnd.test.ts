import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

/**
 * assayCoherence.test.ts tests the judgement. This tests the plumbing, which
 * is the part that silently rots: the module can be perfectly correct while
 * `resolveQuery` never calls it, or calls it before the resolvers have
 * finished, or drops the result on the floor. Every unit test would still
 * pass and no user would ever see a finding.
 *
 * `mm_competitive_inhibition` is used throughout because it is the only
 * domain today that resolves two kinetic parameters (RESOLVABLE_FIELDS),
 * and therefore the only one where coherence has anything to say.
 */

const KM_1974 = {
  found: true,
  km: 10.73,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "740253",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
  },
  assayConditions: { ph: 7.4, temperatureC: 25, unreported: [] },
  literatureCandidates: [],
  logs: [],
};

const KI_2003_DIFFERENT_CONDITIONS = {
  found: true,
  ki: 1.4,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "711801",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
  },
  assayConditions: { ph: 6.0, temperatureC: 37, unreported: [] },
  literatureCandidates: [],
  logs: [],
};

const KI_SAME_PAPER_AS_KM = {
  ...KI_2003_DIFFERENT_CONDITIONS,
  citation: { ...KM_1974.citation },
  assayConditions: { ph: 7.4, temperatureC: 25, unreported: [] },
};

const KI_NO_CONDITIONS = {
  ...KI_2003_DIFFERENT_CONDITIONS,
  assayConditions: { ph: null, temperatureC: null, unreported: ["pH", "temperature"] },
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => KM_1974),
  };
});

// Both km and ki are left to resolution; everything else is supplied.
const CI_QUERY =
  "simulate competitive inhibition of lactate dehydrogenase on lactate " +
  "in Homo sapiens vmax=5 s0=10 i0=1 end=10 points=51";

/** Queue the two per-key lookups in the order queryResolver makes them. */
function queue(km: unknown, ki: unknown) {
  vi.mocked(resolveKineticValue)
    .mockResolvedValueOnce(km as never)
    .mockResolvedValueOnce(ki as never);
}

describe("coherence reaches the caller", () => {
  it("flags a Km and Ki measured under different conditions", async () => {
    queue(KM_1974, KI_2003_DIFFERENT_CONDITIONS);
    const resolved = await resolveQuery(CI_QUERY);

    expect(resolved.assayCoherence.verdict).toBe("differing_conditions");
    expect(resolved.assayCoherence.comparedKeys.sort()).toEqual(["ki", "km"]);
  });

  it("puts the finding in the flags the user already reads", async () => {
    queue(KM_1974, KI_2003_DIFFERENT_CONDITIONS);
    const resolved = await resolveQuery(CI_QUERY);

    // A report on a field nobody inspects is the same as no report. The
    // flags array is what the CLI and the web UI both render.
    const flag = resolved.provenance.flags.find((f) =>
      f.startsWith("Assay coherence:"),
    );
    expect(flag).toBeDefined();
    expect(flag).toMatch(/never true of the same enzyme/i);
  });

  it("recognises when both values came from one paper", async () => {
    queue(KM_1974, KI_SAME_PAPER_AS_KM);
    const resolved = await resolveQuery(CI_QUERY);

    expect(resolved.assayCoherence.verdict).toBe("same_source");
    // Nothing to warn about, so nothing is added to flags.
    expect(
      resolved.provenance.flags.some((f) => f.startsWith("Assay coherence:")),
    ).toBe(false);
  });

  it("does not claim coherence when a value reports no conditions", async () => {
    queue(KM_1974, KI_NO_CONDITIONS);
    const resolved = await resolveQuery(CI_QUERY);

    expect(resolved.assayCoherence.verdict).toBe("unassessable");
    expect(resolved.assayCoherence.excluded.map((e) => e.key)).toContain("ki");
  });

  it("runs AFTER resolution, not before", async () => {
    // If coherence were computed on the pre-resolution provenance it would
    // see two defaults, find nothing resolved, and return `unassessable`
    // forever -- a check that always passes, reported as if it had looked.
    queue(KM_1974, KI_2003_DIFFERENT_CONDITIONS);
    const resolved = await resolveQuery(CI_QUERY);

    expect(resolved.assayCoherence.verdict).not.toBe("unassessable");
    expect(resolved.assayCoherence.spread?.phRange?.delta).toBeCloseTo(1.4, 5);
  });

  it("ignores user-supplied parameters entirely", async () => {
    // km is overridden in the query, so only ki resolves. One resolved
    // parameter is not a pair -- and the user's km must not be treated as
    // an assay that agrees or disagrees with anything.
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(
      KI_2003_DIFFERENT_CONDITIONS as never,
    );
    const resolved = await resolveQuery(
      "simulate competitive inhibition of lactate dehydrogenase on lactate " +
        "in Homo sapiens km=2 vmax=5 s0=10 i0=1 end=10 points=51",
    );

    expect(resolved.assayCoherence.comparedKeys).not.toContain("km");
    expect(resolved.assayCoherence.verdict).toBe("unassessable");
  });
});

describe("the origin filter is load-bearing", () => {
  /**
   * The test above passes for the wrong reason and it is worth saying so.
   *
   * A user-supplied or defaulted parameter has no `assayConditions`, so it
   * is dropped by the conditions check whether or not the origin filter
   * exists. Deleting `origin === "resolved"` therefore breaks nothing that
   * the end-to-end test can see — which was verified by deleting it, and
   * watching all six tests pass.
   *
   * A filter no test can break is a filter that will be removed as dead
   * code by someone tidying up, and the day after that a default carrying
   * conditions will quietly join the comparison. So it is tested at its own
   * level, with the case the resolver does not currently produce and the
   * next feature might.
   */
  it("excludes a non-resolved parameter even when it carries conditions", async () => {
    const { coherenceFromProvenance } = await import("../lib/assayCoherence");

    const report = coherenceFromProvenance({
      km: {
        origin: "resolved",
        assayConditions: { ph: 7.4, temperatureC: 25 },
        citationLocators: [{ kind: "brenda_ref", value: "740253" }],
      },
      // A default that has somehow acquired conditions. If it were counted,
      // this pair would read `differing_conditions` -- a real-sounding
      // finding about a number nobody measured.
      ki: {
        origin: "default",
        assayConditions: { ph: 6.0, temperatureC: 37 },
        citationLocators: [{ kind: "brenda_ref", value: "999999" }],
      },
    });

    expect(report.comparedKeys).toEqual(["km"]);
    expect(report.verdict).toBe("unassessable");
    expect(report.reason).toMatch(/no pair to be incoherent/i);
  });

  it("compares two resolved parameters in the same map", async () => {
    // The counterpart: with both marked resolved, the same conditions DO
    // produce a finding. Without this, the test above could pass because
    // the function returns `unassessable` for everything.
    const { coherenceFromProvenance } = await import("../lib/assayCoherence");

    const report = coherenceFromProvenance({
      km: {
        origin: "resolved",
        assayConditions: { ph: 7.4, temperatureC: 25 },
        citationLocators: [{ kind: "brenda_ref", value: "740253" }],
      },
      ki: {
        origin: "resolved",
        assayConditions: { ph: 6.0, temperatureC: 37 },
        citationLocators: [{ kind: "brenda_ref", value: "999999" }],
      },
    });

    expect(report.verdict).toBe("differing_conditions");
  });
});

/**
 * The effector wiring, tested where it can actually break.
 *
 * `assayCoherence.test.ts` builds `ParameterUnderTest` objects by hand and
 * never goes through `resolveQuery`. So when the resolver was made to stop
 * forwarding `agentResult.effectors`, **all 35 of its tests still passed** —
 * the judgement was intact and the wiring was severed, and nothing could
 * tell the difference.
 *
 * That is the third time this repository has hit the same shape: the origin
 * filter in ADR 0026, the reliability call site in ADR 0027, and here. The
 * lesson each time is that a test which constructs the input cannot verify
 * how the input is produced.
 *
 * These tests exist so the mutation fails.
 */

const FBP_PRESENT_EFFECTOR = {
  raw: "in presence of fructose 1,6-bisphosphate",
  compound_text: "fructose 1,6-bisphosphate",
  presence: "present",
  concentration_text: null,
  identity: { raw: "fructose 1,6-bisphosphate", parent_cid: 172922, status: "resolved" },
};
const FBP_ABSENT_EFFECTOR = {
  ...FBP_PRESENT_EFFECTOR,
  raw: "in absence of fructose 1,6-bisphosphate",
  presence: "absent",
};

/** Both rows report identical pH and temperature, so the ONLY thing that
 * can produce an effector finding is the effector list itself. */
const KM_WITH_FBP = {
  ...KM_1974,
  assayConditions: { ph: 6.0, temperatureC: 25, unreported: [] },
  effectors: [FBP_PRESENT_EFFECTOR],
};
const KI_WITHOUT_FBP = {
  ...KI_2003_DIFFERENT_CONDITIONS,
  assayConditions: { ph: 6.0, temperatureC: 25, unreported: [] },
  effectors: [FBP_ABSENT_EFFECTOR],
};

describe("effectors survive the resolver", () => {
  it("reaches the coherence report through resolveQuery", async () => {
    queue(KM_WITH_FBP, KI_WITHOUT_FBP);
    const resolved = await resolveQuery(CI_QUERY);

    // If the resolver stops passing `agentResult.effectors`, the lists are
    // empty and this reads `not_reported` instead.
    expect(resolved.assayCoherence.effectors?.verdict).toBe("different");
    expect(resolved.assayCoherence.effectors?.reason).toContain("PRESENCE");
  });

  it("carries the raw clauses per parameter", async () => {
    queue(KM_WITH_FBP, KI_WITHOUT_FBP);
    const resolved = await resolveQuery(CI_QUERY);

    expect(resolved.assayCoherence.effectors?.reported["km"]).toEqual([
      "in presence of fructose 1,6-bisphosphate",
    ]);
    expect(resolved.assayCoherence.effectors?.reported["ki"]).toEqual([
      "in absence of fructose 1,6-bisphosphate",
    ]);
  });

  it("does not disturb the pH/temperature verdict", async () => {
    // Identical conditions on both rows. The effector finding rides
    // alongside; folding it in would degrade an established fact.
    queue(KM_WITH_FBP, KI_WITHOUT_FBP);
    const resolved = await resolveQuery(CI_QUERY);

    expect(resolved.assayCoherence.verdict).toBe("same_conditions");
    expect(resolved.assayCoherence.effectors?.verdict).toBe("different");
  });

  it("reports not_reported when the runner sends no effectors", async () => {
    // The counterpart. Without this, the tests above could pass because
    // `resolveQuery` fabricated an effector list from somewhere.
    queue(KM_1974, KI_2003_DIFFERENT_CONDITIONS);
    const resolved = await resolveQuery(CI_QUERY);

    expect(resolved.assayCoherence.effectors?.verdict).toBe("not_reported");
  });
});
