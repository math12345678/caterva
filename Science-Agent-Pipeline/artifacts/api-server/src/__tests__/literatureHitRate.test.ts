/**
 * A published metric must have a writer.
 *
 * GET /api/metrics served three numbers that nothing in the tree ever
 * incremented:
 *
 *     literatureHitRate    always 0
 *     literatureHits       always 0
 *     keywordFallbacks     always 0
 *
 * They were declared, initialised to 0, read by `getSnapshot()`, divided
 * into a percentage, rounded, and published — with no `++` anywhere.
 * `llmAttempts` two fields above them had a writer; these did not. A
 * consumer could not tell the difference between "this system resolves
 * nothing from literature" and "nobody wired the counter", because the
 * wire format is identical.
 *
 * That is exactly the defect Caterva exists to refuse, committed in its
 * own telemetry: a number presented as measured that nobody measured.
 *
 * The gap survived because the only available tests were of the SHAPE of
 * the snapshot. A field initialised to 0 and never written passes every
 * "is a number", "is not negative" and "is at most 100" assertion there
 * is. The test that catches it has to run a real resolve and demand the
 * counter MOVE.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { verifiableMetricsCollector } from "../lib/verifiable-metrics";

beforeEach(() => {
  verifiableMetricsCollector.reset();
});

describe("recordParameterProvenance counts what it says it counts", () => {
  it("splits origins into literature hits and keyword fallbacks", () => {
    verifiableMetricsCollector.recordParameterProvenance([
      "resolved",
      "resolved",
      "default",
      "user",
    ]);
    const snap = verifiableMetricsCollector.getSnapshot();

    expect(snap.resolutionMetrics.literatureHitCount).toBe(2);
    expect(snap.resolutionMetrics.keywordFallbackUsed).toBe(1);
    // Four parameters were sought, so the rate is 2/4 -- NOT 2/3. A "user"
    // origin is still an attempt: the system needed that parameter and did
    // not get it from literature. Excluding the ones we failed to resolve
    // is the flattering way to compute this.
    expect(snap.literatureHitRate).toBeCloseTo(50, 6);
  });

  it("does not reach 100% just because a query succeeded", () => {
    // Every parameter user-supplied: a perfectly successful query with
    // zero literature hits. A rate that reported 100% here would be
    // measuring "did the query work", not "did literature answer".
    verifiableMetricsCollector.recordParameterProvenance(["user", "user"]);
    expect(verifiableMetricsCollector.getSnapshot().literatureHitRate).toBe(0);
  });

  it("reports 0 before anything is recorded, without dividing by zero", () => {
    const snap = verifiableMetricsCollector.getSnapshot();
    expect(snap.literatureHitRate).toBe(0);
    expect(Number.isNaN(snap.literatureHitRate)).toBe(false);
  });
});

describe("the counter is actually wired to the resolver", () => {
  /**
   * The test that would have caught the original defect.
   *
   * Everything above passes against a collector that no production code
   * calls -- which was the state of the tree until 2026-09-05. Only a real
   * resolve proves the call site exists.
   *
   * Deliberately a fully user-supplied query: it needs no network and no
   * BRENDA fixture, so it stays fast and offline, and it still fails if
   * the call site is removed. What it asserts is that the counter MOVED,
   * not what it moved to.
   */
  it("a real resolveQuery moves literatureAttempts off zero", async () => {
    const before = verifiableMetricsCollector.getSnapshot();
    expect(
      before.resolutionMetrics.literatureHitCount +
        before.resolutionMetrics.literatureMissCount,
      "premise: a fresh collector has recorded no attempts",
    ).toBe(0);

    const resolved = await resolveQuery(
      "simulate enzyme kinetics km=2 vmax=5 s0=10 end=10 points=51",
    );
    // Guard the premise: if the query resolved nothing, the assertion
    // below would be checking an empty provenance map.
    expect(Object.keys(resolved.parameterProvenance).length).toBeGreaterThan(0);

    const after = verifiableMetricsCollector.getSnapshot();
    const attempts =
      after.resolutionMetrics.literatureHitCount +
      after.resolutionMetrics.literatureMissCount;
    expect(
      attempts,
      "resolveQuery ran but recorded no parameter provenance -- the " +
        "metric is published with no writer again",
    ).toBe(Object.keys(resolved.parameterProvenance).length);
  }, 60000);

  it("records the refusing path too, not only the resolving one", async () => {
    // A query naming an enzyme with no supplied [E]0 REFUSES (ADR 0013) by
    // throwing, so the recording has to happen before the throw. If it sat
    // after the success branch, refusals would be invisible and the hit
    // rate would be computed over a population selected for having
    // succeeded -- which is the flattering way to be wrong.
    await expect(
      resolveQuery("simulate michaelis menten for hexokinase"),
    ).rejects.toThrow();

    const after = verifiableMetricsCollector.getSnapshot();
    const attempts =
      after.resolutionMetrics.literatureHitCount +
      after.resolutionMetrics.literatureMissCount;
    expect(
      attempts,
      "the query refused and recorded nothing -- the hit rate would only " +
        "ever see queries that succeeded",
    ).toBeGreaterThan(0);
  }, 120000);
});
