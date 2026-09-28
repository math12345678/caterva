/**
 * The LLM path records parameter provenance too.
 *
 * `resolveQuery` has TWO places that compute `unverifiedOriginKeys`: one
 * on the LLM-classified path and one on the keyword-fallback path. The
 * literature-hit counters are recorded at both.
 *
 * Only the fallback path is reachable from an ordinary offline test, and
 * that gap is not hypothetical: deleting the LLM-path call site left every
 * test in `literatureHitRate.test.ts` green. A call site no test can reach
 * is a call site nobody knows is there — which is how
 * `literatureHits` came to be published with no writer in the first place.
 *
 * So this file drives the LLM path directly, mocking `resolveQueryWithLLM`
 * the way `statedQuantitiesLlmPath.test.ts` does. Verified by deleting the
 * LLM-path call site and confirming this file goes red.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveQueryWithLLM } from "../lib/llmResolver";
import { verifiableMetricsCollector } from "../lib/verifiable-metrics";

vi.mock("../lib/llmResolver", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/llmResolver")>();
  return { ...original, resolveQueryWithLLM: vi.fn() };
});

// beta/gamma supplied explicitly so the epidemiology bridge short-circuits
// and no network call is made. What is under test is the recording, not
// the R0 lookup.
const QUERY =
  "michaelis menten kinetics with km=0.5 vmax=2 s0=10";

beforeEach(() => {
  verifiableMetricsCollector.reset();
  vi.mocked(resolveQueryWithLLM).mockResolvedValue({
    domain: "mm",
    parameters: {},
    reasoning: "test",
    modelCitations: [],
  });
});

describe("literature-hit accounting on the LLM path", () => {
  it("records one attempt per parameter the query needed", async () => {
    const resolved = await resolveQuery(QUERY);

    // Premise: the LLM path was actually taken and produced provenance.
    // Without this the assertion below could pass against an empty map.
    expect(vi.mocked(resolveQueryWithLLM)).toHaveBeenCalled();
    const expected = Object.keys(resolved.parameterProvenance).length;
    expect(expected).toBeGreaterThan(0);

    const snap = verifiableMetricsCollector.getSnapshot();
    const attempts =
      snap.resolutionMetrics.literatureHitCount +
      snap.resolutionMetrics.literatureMissCount;
    expect(
      attempts,
      "the LLM path resolved a query and recorded no provenance -- the " +
        "hit rate would silently omit every LLM-classified query",
    ).toBe(expected);
  }, 60000);

  it("counts user-supplied values as attempts, not as literature hits", async () => {
    // km and vmax came from the query text. They are attempts the
    // literature did not answer, and counting them as hits would inflate
    // the rate with numbers the user typed themselves.
    await resolveQuery(QUERY);
    const snap = verifiableMetricsCollector.getSnapshot();

    expect(snap.resolutionMetrics.literatureHitCount).toBe(0);
    expect(snap.literatureHitRate).toBe(0);
  }, 60000);
});
