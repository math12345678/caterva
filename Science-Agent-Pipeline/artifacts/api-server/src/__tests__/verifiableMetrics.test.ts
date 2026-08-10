/**
 * Tests for the metrics collector the pipeline ACTUALLY writes to.
 *
 * `verifiable-metrics.ts` had no test file at all, while
 * `metrics.test.ts` carried 20 tests aimed at `lib/metrics.ts` — a second
 * collector with zero production writers. So the suite's entire metrics
 * coverage pointed at dead code, and the Wilson interval and Harter
 * percentiles published by `/api/simulate/metrics/pipeline` and
 * `/api/dashboard/overview` were exercised by nothing.
 *
 * The Wilson figures below are hand-computed from the closed form rather
 * than captured from this implementation, so they check the code against
 * the statistics instead of against itself:
 *
 *     centre = (p + z²/2n) / (1 + z²/n)
 *     margin = z·√(p(1-p)/n + z²/4n²) / (1 + z²/n)
 *
 * with z = 1.96. Reference values (k successes of n):
 *
 *     9/10   -> [0.595844, 0.982124]
 *     50/100 -> [0.403830, 0.596170]
 *     1/1    -> [0.206543, 1.000000]
 *     0/10   -> [0.000000, 0.277540]
 *
 * Wilson, E. B. (1927), JASA 22(158), 209-212, DOI 10.1080/01621459.1927.10502953.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { verifiableMetricsCollector } from "../lib/verifiable-metrics";

beforeEach(() => {
  verifiableMetricsCollector.reset();
});

function recordOutcomes(successes: number, failures: number): void {
  for (let i = 0; i < successes; i++) {
    verifiableMetricsCollector.recordJobStart(`ok-${i}`);
    verifiableMetricsCollector.recordJobCompletion(`ok-${i}`, 100);
  }
  for (let i = 0; i < failures; i++) {
    verifiableMetricsCollector.recordJobStart(`bad-${i}`);
    verifiableMetricsCollector.recordJobFailure(`bad-${i}`);
  }
}

describe("Wilson score interval (Wilson 1927)", () => {
  it.each([
    [9, 1, 0.595844, 0.982124],
    [50, 50, 0.40383, 0.59617],
    [1, 0, 0.206543, 1.0],
    [0, 10, 0.0, 0.27754],
  ])(
    "%i successes / %i failures matches the closed form",
    (successes, failures, lower, upper) => {
      recordOutcomes(successes, failures);
      const { confidence95 } =
        verifiableMetricsCollector.getSuccessRateWithConfidence();
      expect(confidence95.lower).toBeCloseTo(lower, 5);
      expect(confidence95.upper).toBeCloseTo(upper, 5);
    },
  );

  it("is asymmetric near the boundary, unlike a normal approximation", () => {
    // The property that makes Wilson worth using: at p=1 the naive
    // interval collapses to [1,1], claiming certainty from 1 observation.
    recordOutcomes(1, 0);
    const { rate, confidence95 } =
      verifiableMetricsCollector.getSuccessRateWithConfidence();
    expect(rate).toBe(1);
    expect(confidence95.lower).toBeLessThan(0.5);
    expect(confidence95.upper).toBe(1);
  });

  it("narrows as the sample grows at a fixed rate", () => {
    recordOutcomes(9, 1);
    const small = verifiableMetricsCollector.getSuccessRateWithConfidence();
    verifiableMetricsCollector.reset();
    recordOutcomes(900, 100);
    const large = verifiableMetricsCollector.getSuccessRateWithConfidence();

    expect(large.rate).toBeCloseTo(small.rate, 6);
    const widthSmall = small.confidence95.upper - small.confidence95.lower;
    const widthLarge = large.confidence95.upper - large.confidence95.lower;
    expect(widthLarge).toBeLessThan(widthSmall / 5);
  });

  it("never reports an interval outside [0, 1]", () => {
    for (const [s, f] of [[0, 1], [1, 0], [0, 1000], [1000, 0]]) {
      verifiableMetricsCollector.reset();
      recordOutcomes(s!, f!);
      const { confidence95 } =
        verifiableMetricsCollector.getSuccessRateWithConfidence();
      expect(confidence95.lower).toBeGreaterThanOrEqual(0);
      expect(confidence95.upper).toBeLessThanOrEqual(1);
      expect(confidence95.lower).toBeLessThanOrEqual(confidence95.upper);
    }
  });
});

describe("latency percentiles (Harter 1974)", () => {
  it("p95 is the value 95% of samples fall at or below", () => {
    // 1..100 ms. The 95th percentile of this set is 95 by definition.
    for (let ms = 1; ms <= 100; ms++) {
      verifiableMetricsCollector.recordJobStart(`j-${ms}`);
      verifiableMetricsCollector.recordJobCompletion(`j-${ms}`, ms);
    }
    const { mean, median, p95, p99 } =
      verifiableMetricsCollector.getLatencyPercentiles();
    expect(mean).toBeCloseTo(50.5, 6);
    expect(median).toBe(51); // upper-median of an even-sized set
    expect(p95).toBe(95);
    expect(p99).toBe(99);
  });

  it("p95 is robust to a single extreme outlier, unlike the mean", () => {
    // The stated reason for publishing P95 rather than the mean.
    for (let ms = 1; ms <= 99; ms++) {
      verifiableMetricsCollector.recordJobStart(`j-${ms}`);
      verifiableMetricsCollector.recordJobCompletion(`j-${ms}`, ms);
    }
    verifiableMetricsCollector.recordJobStart("outlier");
    verifiableMetricsCollector.recordJobCompletion("outlier", 1_000_000);

    const { mean, p95 } = verifiableMetricsCollector.getLatencyPercentiles();
    expect(mean).toBeGreaterThan(9_000); // one outlier wrecks it
    expect(p95).toBeLessThan(200); // p95 barely moves
  });

  it("returns zeros rather than NaN when nothing has run", () => {
    const { mean, median, p95, p99 } =
      verifiableMetricsCollector.getLatencyPercentiles();
    for (const value of [mean, median, p95, p99]) {
      expect(Number.isFinite(value)).toBe(true);
      expect(value).toBe(0);
    }
  });
});

describe("the snapshot does not fabricate rates from an empty sample", () => {
  it("reports sampleCount so a rate can be told apart from no data", () => {
    // /api/metrics/health reported "healthy, 100.0%" on a fresh process,
    // computed from zero observations, and was structurally incapable of
    // ever returning `degraded`.
    const snapshot = verifiableMetricsCollector.getSnapshot();
    expect(snapshot.sampleCount).toBe(0);
    expect(snapshot.completedJobs).toBe(0);
    expect(snapshot.failedJobs).toBe(0);
  });

  it("sampleCount equals completed + failed once jobs run", () => {
    recordOutcomes(7, 3);
    const snapshot = verifiableMetricsCollector.getSnapshot();
    expect(snapshot.sampleCount).toBe(10);
    expect(snapshot.completedJobs).toBe(7);
    expect(snapshot.failedJobs).toBe(3);
  });

  it("activeJobs falls back to zero as jobs settle (Little's Law state)", () => {
    verifiableMetricsCollector.recordJobStart("a");
    verifiableMetricsCollector.recordJobStart("b");
    expect(verifiableMetricsCollector.getSnapshot().activeJobs).toBe(2);

    verifiableMetricsCollector.recordJobCompletion("a", 10);
    verifiableMetricsCollector.recordJobFailure("b");
    expect(verifiableMetricsCollector.getSnapshot().activeJobs).toBe(0);
  });

  it("reset clears every counter", () => {
    recordOutcomes(5, 5);
    verifiableMetricsCollector.recordDomainUsage("mm", 12, true);
    verifiableMetricsCollector.recordStageExecution("Validation", 3, true);
    verifiableMetricsCollector.reset();

    const snapshot = verifiableMetricsCollector.getSnapshot();
    expect(snapshot.sampleCount).toBe(0);
    expect(Object.keys(snapshot.stageMetrics)).toEqual([]);
    expect(Object.keys(snapshot.domainMetrics)).toEqual([]);
  });
});

describe("domain and stage tracking", () => {
  it("records a domain only once it is actually used", () => {
    // The live collector builds its domain map lazily, so it cannot drift
    // from the engine's domain list the way a hardcoded array can — the
    // dead collector's test asserted a 12-entry literal against a copy of
    // itself and could not notice the engine had 16.
    expect(verifiableMetricsCollector.getSnapshot().domainMetrics).toEqual({});
    verifiableMetricsCollector.recordDomainUsage("lotka_volterra", 20, true);
    const { domainMetrics } = verifiableMetricsCollector.getSnapshot();
    expect(Object.keys(domainMetrics)).toEqual(["lotka_volterra"]);
    expect(domainMetrics["lotka_volterra"]!.count).toBe(1);
  });

  it("averages stage duration across executions", () => {
    verifiableMetricsCollector.recordStageExecution("Validation", 10, true);
    verifiableMetricsCollector.recordStageExecution("Validation", 20, true);
    verifiableMetricsCollector.recordStageExecution("Validation", 30, false);
    const stage =
      verifiableMetricsCollector.getSnapshot().stageMetrics["Validation"]!;
    expect(stage.successCount).toBe(2);
    expect(stage.failureCount).toBe(1);
    expect(stage.avgDurationMs).toBeCloseTo(20, 6);
  });
});
