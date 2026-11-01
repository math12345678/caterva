/**
 * A warning must say what is wrong.
 *
 * guardSerializationProvenance serves a degraded-but-real response rather
 * than 500-ing (Rule 2: reject the impossible, flag the implausible), and
 * that is right. But its flag read:
 *
 *     "parameter provenance is incomplete for one or more parameters
 *      (see server log for details)"
 *
 * Nobody using a hosted API can see the server log. The flag told a
 * reader something was wrong and then withheld what -- worse than
 * silence, because it spends trust without buying understanding, in a
 * product whose entire claim is that its numbers can be checked.
 *
 * The violations were already specific ("kcat has a parameter value but
 * no provenance"); they simply were not surfaced.
 *
 * This condition should now be unreachable on known paths (see
 * responseParameterCompleteness.test.ts, which fixed the one live cause),
 * so it is exercised directly rather than through a route. A defensive
 * message with no test is a message nobody has read.
 */
import { describe, expect, it } from "vitest";

import { guardSerializationProvenanceForTests } from "../routes/simulate";
import type * as queue from "../lib/queue";

function responseWith(
  parameters: Record<string, unknown>,
  parameterProvenance: Record<string, unknown>,
): queue.SimulationResponse {
  return {
    runId: "test-run",
    domain: "mm",
    parameters,
    trajectory: [],
    provenance: { reasoning: "", modelCitations: [], flags: [] },
    parameterProvenance,
  } as unknown as queue.SimulationResponse;
}

describe("the provenance-incompleteness flag names the violations", () => {
  it("says WHICH parameter is unaccounted for", () => {
    // A value with no provenance entry.
    const result = responseWith({ km: 2, kcat: 118 }, { km: { origin: "user" } });
    guardSerializationProvenanceForTests(result);

    expect(result.provenance.flags).toHaveLength(1);
    const flag = result.provenance.flags[0]!;
    expect(flag).toContain("kcat");
    // The thing it replaced.
    expect(flag).not.toMatch(/see server log/i);
  });

  it("stays silent when provenance is sound", () => {
    const result = responseWith({ km: 2 }, { km: { origin: "user" } });
    guardSerializationProvenanceForTests(result);
    expect(result.provenance.flags).toEqual([]);
  });

  it("caps a long violation list instead of dumping all of it", () => {
    // Ten unaccounted parameters must not produce an unreadable wall.
    const parameters: Record<string, number> = {};
    for (let i = 0; i < 10; i++) parameters[`p${i}`] = i;
    const result = responseWith(parameters, {});
    guardSerializationProvenanceForTests(result);

    const flag = result.provenance.flags[0]!;
    expect(flag).toMatch(/and \d+ more/);
    // Still names some of them -- a cap that named none would be the old
    // defect wearing a different sentence.
    expect(flag).toContain("p0");
    // ...and genuinely stops. Asserting only the "and N more" suffix
    // passed even with the cap removed, because the suffix survived while
    // the list dumped all ten -- a message that contradicts itself.
    expect(flag).not.toContain("p9");
    expect(flag.match(/has a parameter value but no provenance/g) ?? []).toHaveLength(5);
  });

  it("does not duplicate the flag if the guard runs twice", () => {
    const result = responseWith({ km: 2, kcat: 118 }, { km: { origin: "user" } });
    guardSerializationProvenanceForTests(result);
    guardSerializationProvenanceForTests(result);
    expect(result.provenance.flags).toHaveLength(1);
  });
});
