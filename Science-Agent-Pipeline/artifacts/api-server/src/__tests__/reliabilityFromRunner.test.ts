import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

/**
 * The runner's reliability score must reach the response UNCHANGED.
 *
 * WHY THIS TEST EXISTS, AND WHY THE PARITY TEST WAS NOT ENOUGH
 * -----------------------------------------------------------
 * `science_agent_runner.py` has always graded every resolved value on
 * Bakker's three axes and emitted the result. The API server threw that
 * away and ran the TypeScript grader instead — with no `reference`
 * argument, because none was reachable at that call site. So
 * `conditionProximity` came back `not_assessed` on every request the API
 * server ever served. Not sometimes: always.
 *
 * The CLI, meanwhile, consumed the Python score and reported real grades.
 * Two front ends, one of them structurally incapable of the answer.
 *
 * And `reliabilityScore.test.ts` asserted the two implementations agreed —
 * truthfully, and uselessly. **A parity test pins two implementations
 * against a shared fixture. It says nothing about a call site that hands
 * one of them different arguments.** Both graders would return
 * `not_assessed` for a call with no reference; they agreed perfectly on a
 * question neither was being asked.
 *
 * HOW THIS TEST CATCHES IT
 * ------------------------
 * The mocked runner returns `conditionProximity: "near"`. That grade is
 * *unreachable* by recomputation at this call site: producing `near`
 * requires a PhysiologicalReference, and the API server has none to pass.
 * So if this assertion passes, the score can only have come from the
 * runner.
 *
 * Choosing a grade the wrong implementation cannot produce is what makes a
 * pass-through testable at all. Asserting on `not_assessed` would have been
 * satisfied by the bug.
 */

// `as const` so the grade strings narrow to the ReliabilityScore unions
// rather than widening to `string`. Added when ScienceAgentResult gained
// a typed `reliability` field; the fixture predates it.
const RUNNER_SCORE = {
  assayCompleteness: {
    grade: "complete",
    reason:
      "Assay reports pH 7.4 and 37 C, meeting STRENDA's minimum. The " +
      "measurement can be compared against another lab's figure.",
  },
  conditionProximity: {
    // The tell. Unreachable without a reference the API server cannot supply.
    grade: "near",
    reason:
      "Measured within tolerance of the modelled conditions. Reference " +
      "basis: human blood plasma, stated by the caller.",
  },
  organismMatch: {
    grade: "exact",
    reason: "Measured in Homo sapiens, the organism asked about.",
  },
  noAggregateReason:
    "The three axes are reported separately and deliberately not combined. " +
    "See ADR 0024, Decision 3.",
} as const;

const RESOLVED_WITH_SCORE = {
  found: true,
  km: 2.5,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  reliability: RUNNER_SCORE,
  citation: {
    source: "BRENDA",
    referenceId: "740253",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
  },
  assayConditions: { ph: 7.4, temperatureC: 37 },
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => RESOLVED_WITH_SCORE),
  };
});

const QUERY =
  "simulate michaelis menten of lactate dehydrogenase on lactate in " +
  "Homo sapiens vmax=5 s0=10 end=10 points=51";

describe("the runner's reliability score is the score", () => {
  it("passes conditionProximity through, a grade recomputation cannot reach", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(RESOLVED_WITH_SCORE);
    const resolved = await resolveQuery(QUERY);

    const reliability = resolved.parameterProvenance["km"]?.reliability;
    expect(reliability).toBeDefined();
    expect(reliability!.conditionProximity.grade).toBe("near");
    // Stated explicitly: this is the assertion that fails if anyone
    // reintroduces a local grader at this call site.
    expect(reliability!.conditionProximity.grade).not.toBe("not_assessed");
  });

  it("passes every axis through verbatim, reasons included", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(RESOLVED_WITH_SCORE);
    const resolved = await resolveQuery(QUERY);
    const reliability = resolved.parameterProvenance["km"]!.reliability!;

    expect(reliability.assayCompleteness).toEqual(RUNNER_SCORE.assayCompleteness);
    expect(reliability.conditionProximity).toEqual(RUNNER_SCORE.conditionProximity);
    expect(reliability.organismMatch).toEqual(RUNNER_SCORE.organismMatch);
  });

  it("still offers no total", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(RESOLVED_WITH_SCORE);
    const resolved = await resolveQuery(QUERY);
    const reliability = resolved.parameterProvenance["km"]!.reliability!;

    expect(reliability).not.toHaveProperty("total");
    expect(reliability).not.toHaveProperty("score");
    expect(reliability.noAggregateReason).toContain("ADR 0024");
  });

  it("reports an absent score as absent rather than substituting one", async () => {
    // A fallback grader was considered and rejected: a score computed
    // locally would be indistinguishable in the response from one computed
    // by the resolver, which is how the drift started.
    const withoutScore = { ...RESOLVED_WITH_SCORE, reliability: undefined };
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(withoutScore);
    const resolved = await resolveQuery(QUERY);

    expect(resolved.parameterProvenance["km"]?.reliability).toBeUndefined();
  });
});
