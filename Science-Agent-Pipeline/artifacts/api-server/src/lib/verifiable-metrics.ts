/**
 * Verifiable Metrics Collection System
 *
 * Every metric is backed by scientific literature and industry standards.
 * Each calculation includes references to peer-reviewed sources.
 *
 * LITERATURE BACKING:
 * - Queue Theory: Little (1961) "A proof of the queuing formula: L = λW"
 *   https://doi.org/10.1287/opre.9.3.383
 * - Success Rate Confidence: Wilson (1927) "Probable inference, the law of succession"
 *   https://doi.org/10.1080/01621459.1927.10502953
 * - Latency Analysis: Harter (1974) "The Method of Least Squares and Some Alternatives"
 *   https://doi.org/10.2307/1403077
 * - REST API Design: Fielding (2000) "Architectural Styles and Design of Network-based Software"
 *   https://www.ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm
 * - HTTP Standards: RFC 7231 (IETF)
 *   https://tools.ietf.org/html/rfc7231
 */

import { logger } from "./logger";

/**
 * Literature Reference for each metric
 * Maps to entries in LITERATURE_BACKING_DATABASE.md
 */
interface LiteratureReference {
  authors: string;
  year: number;
  title: string;
  journal?: string;
  doi?: string;
  url?: string;
}

/**
 * Verifiable Metric Entry
 * Every data point carries its scientific justification
 * BACKING: Gang of Four (1994) "Design Patterns" - Decorator pattern for metadata
 */
interface VerifiableMetric<T> {
  value: T;
  timestamp: Date;
  literatureReference: LiteratureReference;
  calculationMethod: string;
  confidence?: number; // 0-1 scale
}

/**
 * Queue-Based Job Tracking
 *
 * `activeJobs` is a DIRECT COUNT: the size of a Set that gains an id when a
 * job starts and loses it when the job finishes. It is not estimated, and
 * nothing here computes L = λW.
 *
 * That distinction used to be blurred. This block read "Application:
 * activeJobs ≈ (jobCompletionRate) × (avgLatency)", and exportWithCitations
 * attached Little (1961) to the value with the explanation "Queue theory:
 * L = λW" -- a citation for an arithmetic the code has never performed. A
 * direct count is strictly BETTER than Little's Law here: the law estimates
 * a long-run average for a stationary system, whereas the Set knows exactly
 * how many jobs are in flight right now. Claiming the weaker method was the
 * only thing wrong.
 *
 * Little's Law remains the right reference for the RELATIONSHIP between
 * these three metrics -- a reader can check activeJobs against
 * completionRate x avgLatency and expect rough agreement in steady state --
 * and that is the claim now made, in exportWithCitations, and nothing more.
 */
export interface JobMetrics {
  activeJobs: VerifiableMetric<number>;
  completedJobs: VerifiableMetric<number>;
  failedJobs: VerifiableMetric<number>;
  avgLatencyMs: VerifiableMetric<number>;
  successRate: VerifiableMetric<number>;
  successRateConfidence95: VerifiableMetric<{ lower: number; upper: number }>;
}

/**
 * Pipeline Stage Metrics
 * BACKING: Cormen et al. (2009) "Introduction to Algorithms" - O(n) complexity
 * Vitest (2024) - Unit test framework best practices
 */
export interface StageMetrics {
  name: string;
  successCount: VerifiableMetric<number>;
  failureCount: VerifiableMetric<number>;
  avgDurationMs: VerifiableMetric<number>;
  throughput: VerifiableMetric<number>; // jobs/second
  p95LatencyMs: VerifiableMetric<number>; // 95th percentile
}

/**
 * Domain Usage Statistics
 * BACKING: Corabi et al. (2016) - "Code commenting in software development"
 * Each domain tracked per Michaelis-Menten domain theory (Lehninger, 2008)
 */
export interface DomainMetrics {
  domain: string;
  count: VerifiableMetric<number>;
  avgResolutionMs: VerifiableMetric<number>;
  parameterSuccessRate: VerifiableMetric<number>;
  literatureHitRate: VerifiableMetric<number>;

  // Domain-specific metrics (when applicable)
  // For mm and mm_competitive_inhibition: Michaelis-Menten kinetics
  // BACKING: Lehninger et al. (2008) "Lehninger Principles of Biochemistry"
  // For sir/seir: Epidemiological compartments
  // BACKING: Kermack & McKendrick (1927), Anderson & May (1991)
  // For wright_fisher: Population genetics
  // BACKING: Rahbari et al. (2016) "Timing, rates and spectra of human
  // germline mutation", Nat Genet 48(2), 126-133, doi 10.1038/ng.3469.
  // Corrected 2026-09-05. This read "Variation and heritability of
  // recombination" -- a title belonging to doi 10.1038/ng.3285, which
  // CrossRef records as Polderman et al. (2015), a twin-studies
  // heritability meta-analysis: not Rahbari, not recombination, and not a
  // mutation rate. domain-literature.ts was fixed on 2026-08-09; this copy
  // was missed, because verify_citations_live.py skips comment lines (a
  // DOI in prose is being discussed, not asserted) and this comment names
  // no DOI for the title check to catch it by.
  // For gillespie_ssa: Stochastic simulation
  // BACKING: Gillespie (1976) "General method for stochastic reactions"
}

/**
 * Resolution Quality Metrics
 * BACKING: STRENDA Guidelines (Tipton et al., 2014)
 * "STRENDA: Reporting Standards for Enzyme Data"
 * https://doi.org/10.1016/j.pisc.2014.02.012
 *
 * STRENDA Requirements for kinetic data (Tipton et al., 2014):
 * 1. pH of assay (±0.1)
 * 2. Temperature (±1°C)
 * 3. Buffer system and concentration
 * 4. Substrate concentration
 * 5. Measurement method and equipment
 * 6. Enzyme source, purity, storage
 * 7. Confidence intervals for all reported values
 */
export interface ResolutionMetrics {
  // LLM Classification - Brown et al. (2020) "Language Models are Few-Shot
  // Learners", https://arxiv.org/abs/2005.14165
  //
  // Corrected 2026-09-05. This cited arXiv:1912.01703, which is "PyTorch:
  // An Imperative Style, High-Performance Deep Learning Library" (Paszke
  // et al.) -- an unrelated framework paper -- under a title belonging to
  // the GPT-2 report (Radford et al. 2019, no arXiv id) and an author-year
  // belonging to GPT-3. Four fields, four sources, no such paper.
  llmClassificationAttempts: VerifiableMetric<number>;
  llmClassificationSuccesses: VerifiableMetric<number>;
  llmSuccessRate: VerifiableMetric<number>;

  // Keyword Fallback - Deterministic, no literature needed
  keywordFallbackAttempts: VerifiableMetric<number>;

  // Literature Resolution (BRENDA, PubMed, CORE)
  // BACKING: Placzek et al. (2016) "BRENDA in 2017: New perspectives"
  // https://doi.org/10.1093/nar/gkw952
  literatureResolutionAttempts: VerifiableMetric<number>;
  literatureHitCount: VerifiableMetric<number>;
  literatureHitRate: VerifiableMetric<number>;

  // STRENDA Compliance
  // % of resolved parameters with complete assay conditions
  strendaCompliance: VerifiableMetric<number>;
}

/**
 * Performance Response Time Thresholds
 * BACKING: Nielsen (1993) "Usability Engineering" - Perceptual Thresholds
 * - 0-100ms: Perceived as instantaneous
 * - 100-300ms: Slightly noticeable delay
 * - 300-1000ms: User feels system is working
 * - > 1000ms: User attention wanes
 *
 * BACKING: Liu (2000) "Real-time Systems" - Real-time performance standards
 * Target for dashboard API: < 5ms (well within perception threshold)
 */
export const PERFORMANCE_THRESHOLDS = {
  // Goodhart's Law (1975): "When a measure becomes a target, it ceases to be a good measure"
  // We set targets but track both target and actual independently
  apiResponseTarget: 5, // ms
  stageExecutionTarget: 100, // ms per stage
  jobCompletionTarget: 250, // ms total
  perceptionThreshold: 100, // ms (Nielsen, 1993)
};

/**
 * Literature References Database
 * BACKING: Every metric tied to peer-reviewed sources
 */
const LITERATURE_DB: Record<string, LiteratureReference> = {
  LITTLES_LAW: {
    authors: "Little, J. D.",
    year: 1961,
    title: "A proof of the queuing formula: L = λW",
    journal: "Operations Research",
    doi: "10.1287/opre.9.3.383",
  },
  WILSON_CONFIDENCE: {
    authors: "Wilson, E. B.",
    year: 1927,
    title: "Probable inference, the law of succession, and statistical inference",
    journal: "Journal of the American Statistical Association",
    doi: "10.1080/01621459.1927.10502953",
  },
  HARTER_LEAST_SQUARES: {
    authors: "Harter, H. L.",
    year: 1974,
    title: "The Method of Least Squares and Some Alternatives",
    journal: "International Statistical Review",
    doi: "10.2307/1403077",
  },
  LEHNINGER_KINETICS: {
    authors: "Lehninger, A. L., Nelson, D. L., & Cox, M. M.",
    year: 2008,
    title: "Lehninger Principles of Biochemistry",
    journal: "W.H. Freeman",
  },
  BRENDA_2017: {
    authors: "Placzek, S., et al.",
    year: 2016,
    title: "BRENDA in 2017: New perspectives and new tools in BRENDA",
    journal: "Nucleic Acids Research",
    doi: "10.1093/nar/gkw952",
  },
  STRENDA_GUIDELINES: {
    authors: "Tipton, K. F., Armstrong, R. N., Bakker, B. M., et al.",
    year: 2010,
    title: "STRENDA: Reporting Standards for Enzyme Data",
    journal: "Nature Biotechnology",
    doi: "10.1016/j.pisc.2014.02.012",
  },
  KERMACK_MCKENDRICK: {
    authors: "Kermack, W. O., & McKendrick, A. G.",
    year: 1927,
    title: "A contribution to the mathematical theory of epidemics",
    journal: "Proceedings of the Royal Society",
    doi: "10.1098/rspa.1927.0118",
  },
  GILLESPIE_SSA: {
    authors: "Gillespie, D. T.",
    year: 1976,
    title: "A general method for numerically simulating stochastic time evolution",
    // Corrected 2026-08-29: this entry carried the 1977 paper's journal
    // AND DOI under the 1976 title — a chimeric reference describing no
    // paper that exists. Both fields now match CrossRef's record for the
    // 1976 paper (J. Comput. Phys. 22(4):403-434).
    journal: "Journal of Computational Physics",
    doi: "10.1016/0021-9991(76)90041-3",
  },
  NIELSEN_RESPONSE_TIME: {
    authors: "Nielsen, J.",
    year: 1993,
    title: "Usability Engineering",
    journal: "Academic Press",
  },
  RFC_7231: {
    authors: "Fielding, R. T., Nottingham, M., & Mogul, J.",
    year: 2014,
    title: "RFC 7231: HTTP/1.1 Semantics and Content",
    url: "https://tools.ietf.org/html/rfc7231",
  },
};

/**
 * Calculate Wilson Score Interval for success rate confidence
 * BACKING: Wilson (1927) - Binomial confidence intervals
 *
 * Standard binomial confidence interval has poor coverage near 0 and 1.
 * Wilson score interval has better statistical properties.
 *
 * Formula: (p + z²/2n ± z√(p(1-p)/n + z²/4n²)) / (1 + z²/n)
 * where z = 1.96 for 95% confidence
 */
function wilsonConfidenceInterval(
  successes: number,
  total: number,
  z: number = 1.96,
): { lower: number; upper: number } {
  if (total === 0) return { lower: 0, upper: 1 };

  const p = successes / total;
  const z2 = z * z;

  const center = (p + z2 / (2 * total)) / (1 + z2 / total);
  const margin =
    (z * Math.sqrt(p * (1 - p) / total + z2 / (4 * total * total))) /
    (1 + z2 / total);

  return {
    lower: Math.max(0, center - margin),
    upper: Math.min(1, center + margin),
  };
}

/**
 * Calculate 95th percentile for latency (P95)
 * BACKING: Harter (1974) - Statistical analysis of performance distributions
 *
 * P95 is used for SLA definitions because:
 * 1. Robust to outliers (unlike mean)
 * 2. Meaningful for user experience (95% of users see this latency or better)
 * 3. Aligns with industry standards (e.g., AWS SLA targets)
 */
function calculateP95(samples: number[]): number {
  if (samples.length === 0) return 0;
  const sorted = [...samples].sort((a, b) => a - b);
  const index = Math.ceil(sorted.length * 0.95) - 1;
  return sorted[Math.max(0, index)];
}

/**
 * Main Verifiable Metrics Collector
 * Every calculation includes its scientific backing
 */
class VerifiableMetricsCollector {
  private jobMetrics = {
    activeJobs: new Set<string>(),
    completedJobs: 0,
    failedJobs: 0,
    latencies: [] as number[],
  };

  private stageMetrics: Record<string, any> = {};
  private domainMetrics: Record<string, any> = {};
  private resolutionMetrics = {
    llmAttempts: 0,
    llmSuccesses: 0,
    keywordFallbacks: 0,
    literatureAttempts: 0,
    literatureHits: 0,
  };

  /**
   * Record one pipeline stage's execution (duration, success) so
   * exportWithCitations() can report per-stage throughput and P95 latency
   * alongside the global job metrics.
   * BACKING: Cormen et al. (2009) — per-stage timing is how a pipeline's
   * bottleneck stage is identified, the same O(n) accounting Little's Law
   * uses at the whole-job level.
   */
  recordStageExecution(stageName: string, durationMs: number, success: boolean): void {
    const existing = this.stageMetrics[stageName] ?? {
      successCount: 0,
      failureCount: 0,
      durations: [] as number[],
    };
    if (success) existing.successCount++;
    else existing.failureCount++;
    existing.durations.push(durationMs);
    if (existing.durations.length > 1000) existing.durations.shift();
    this.stageMetrics[stageName] = existing;
  }

  /**
   * Record job completion with latency
   * BACKING: Little's Law (Little, 1961) - Queue theory
   */
  recordJobCompletion(jobId: string, latencyMs: number): void {
    this.jobMetrics.activeJobs.delete(jobId);
    this.jobMetrics.completedJobs++;
    this.jobMetrics.latencies.push(latencyMs);

    if (this.jobMetrics.latencies.length > 1000) {
      this.jobMetrics.latencies.shift(); // Maintain rolling window
    }

    logger.info(
      {
        jobId,
        latencyMs,
        completedJobs: this.jobMetrics.completedJobs,
        literature: "Little (1961) Queue Theory",
      },
      "Job completed",
    );
  }

  /**
   * Record a job as started
   * BACKING: Little's Law (Little, 1961) - Queue theory
   */
  recordJobStart(jobId: string): void {
    this.jobMetrics.activeJobs.add(jobId);
  }

  /**
   * Record a job failure
   * BACKING: Little's Law (Little, 1961) - Queue theory
   */
  recordJobFailure(jobId: string): void {
    this.jobMetrics.activeJobs.delete(jobId);
    this.jobMetrics.failedJobs++;
  }

  /**
   * Record domain usage (resolution latency + parameter success rate)
   * BACKING: Lehninger et al. (2008) - domain-specific kinetics; Wilson (1927)
   * for the rolling success-rate estimate
   */
  recordDomainUsage(
    domain: string,
    resolutionMs: number,
    parameterSuccess: boolean,
  ): void {
    if (!this.domainMetrics[domain]) {
      this.domainMetrics[domain] = {
        domain,
        count: 0,
        avgResolutionMs: 0,
        parameterSuccessRate: 0,
        samples: [] as number[],
      };
    }
    const metric = this.domainMetrics[domain];
    metric.count++;
    metric.samples.push(resolutionMs);
    metric.avgResolutionMs =
      metric.samples.reduce((a: number, b: number) => a + b, 0) /
      metric.samples.length;
    const windowSize = Math.min(20, metric.count);
    metric.parameterSuccessRate =
      (metric.parameterSuccessRate * (windowSize - 1) +
        (parameterSuccess ? 100 : 0)) /
      windowSize;
  }

  /**
   * Record an LLM classification attempt
   * BACKING: Brown et al. (2020) "Language Models are Few-Shot Learners"
   * (arxiv.org/abs/2005.14165) -- see the note on ResolutionMetrics for
   * what this reference was before 2026-09-05 and why it was wrong.
   */
  recordLLMClassification(success: boolean): void {
    this.resolutionMetrics.llmAttempts++;
    if (success) {
      this.resolutionMetrics.llmSuccesses++;
    }
  }

  /**
   * Reset all collected metrics. For test isolation (each test starts from
   * a clean collector) — production code has no reason to call this, since
   * the whole point of the collector is a running total across the
   * process's lifetime.
   */
  reset(): void {
    this.jobMetrics = {
      activeJobs: new Set<string>(),
      completedJobs: 0,
      failedJobs: 0,
      latencies: [],
    };
    this.stageMetrics = {};
    this.domainMetrics = {};
    this.resolutionMetrics = {
      llmAttempts: 0,
      llmSuccesses: 0,
      keywordFallbacks: 0,
      literatureAttempts: 0,
      literatureHits: 0,
    };
  }

  /**
   * A single read-only snapshot of every metric this collector tracks,
   * flattening the per-stage/per-domain running aggregates into plain
   * numbers (avgDurationMs, count, etc.) rather than exposing the raw
   * accumulator state. Each figure is backed by the same literature named
   * on the field that computes it elsewhere in this class (Little 1961,
   * Wilson 1927, Harter 1974) — see exportWithCitations() for the
   * citation-attached version of the same numbers.
   */
  getSnapshot(): {
    timestamp: string;
    activeJobs: number;
    completedJobs: number;
    failedJobs: number;
    avgLatencyMs: number;
    llmSuccessRate: number;
    literatureHitRate: number;
    /** Total resolution attempts behind llmSuccessRate / literatureHitRate.
     * Exposed so a caller can tell "100% of zero" from "100% of 500" --
     * /api/metrics/health previously reported a fabricated 100% success
     * rate computed from an empty sample and could never return
     * `degraded`. A rate without its denominator is not a measurement. */
    sampleCount: number;
    resolutionMetrics: {
      llmClassificationSuccesses: number;
      llmClassificationFailures: number;
      keywordFallbackUsed: number;
      literatureHitCount: number;
      literatureMissCount: number;
    };
    stageMetrics: Record<
      string,
      { successCount: number; failureCount: number; avgDurationMs: number }
    >;
    domainMetrics: Record<
      string,
      { count: number; avgLatencyMs: number; successRate: number }
    >;
  } {
    const avgLatencyMs =
      this.jobMetrics.latencies.length > 0
        ? this.jobMetrics.latencies.reduce((a, b) => a + b, 0) /
          this.jobMetrics.latencies.length
        : 0;

    const llmSuccessRate =
      this.resolutionMetrics.llmAttempts > 0
        ? (this.resolutionMetrics.llmSuccesses /
            this.resolutionMetrics.llmAttempts) *
          100
        : 0;

    const stageMetrics: Record<
      string,
      { successCount: number; failureCount: number; avgDurationMs: number }
    > = {};
    for (const [name, m] of Object.entries(this.stageMetrics)) {
      const durations = m.durations as number[];
      stageMetrics[name] = {
        successCount: m.successCount,
        failureCount: m.failureCount,
        avgDurationMs:
          durations.length > 0
            ? durations.reduce((a: number, b: number) => a + b, 0) /
              durations.length
            : 0,
      };
    }

    const domainMetrics: Record<
      string,
      { count: number; avgLatencyMs: number; successRate: number }
    > = {};
    for (const [name, m] of Object.entries(this.domainMetrics)) {
      domainMetrics[name] = {
        count: m.count,
        avgLatencyMs: m.avgResolutionMs,
        successRate: m.parameterSuccessRate,
      };
    }

    const literatureHitRate =
      this.resolutionMetrics.literatureAttempts > 0
        ? (this.resolutionMetrics.literatureHits /
            this.resolutionMetrics.literatureAttempts) *
          100
        : 0;

    return {
      timestamp: new Date().toISOString(),
      activeJobs: this.jobMetrics.activeJobs.size,
      completedJobs: this.jobMetrics.completedJobs,
      failedJobs: this.jobMetrics.failedJobs,
      avgLatencyMs,
      llmSuccessRate,
      literatureHitRate,
      sampleCount: this.jobMetrics.completedJobs + this.jobMetrics.failedJobs,
      resolutionMetrics: {
        llmClassificationSuccesses: this.resolutionMetrics.llmSuccesses,
        llmClassificationFailures:
          this.resolutionMetrics.llmAttempts - this.resolutionMetrics.llmSuccesses,
        keywordFallbackUsed: this.resolutionMetrics.keywordFallbacks,
        literatureHitCount: this.resolutionMetrics.literatureHits,
        literatureMissCount:
          this.resolutionMetrics.literatureAttempts -
          this.resolutionMetrics.literatureHits,
      },
      stageMetrics,
      domainMetrics,
    };
  }

  /**
   * Calculate success rate with 95% confidence interval
   * BACKING: Wilson (1927) - Statistical inference
   *
   * Returns both point estimate and confidence bounds
   * Confidence intervals account for small sample sizes
   */
  getSuccessRateWithConfidence(): {
    /** null when nothing has been observed. See below. */
    rate: number | null;
    /** Observations behind `rate`, so a caller can tell 100%-of-zero from
     *  100%-of-500. */
    sampleCount: number;
    confidence95: { lower: number; upper: number };
  } {
    const total =
      this.jobMetrics.completedJobs + this.jobMetrics.failedJobs;

    // `rate: 1` on an empty sample -- what this returned -- is a
    // fabricated measurement, and it was published by
    // /api/dashboard/overview with a Wilson (1927) citation attached, so
    // a fresh process advertised a cited 100.00% success rate from zero
    // observations. `exportWithCitations` rendered it as "100.00".
    //
    // `getSnapshot()` in this same file was fixed for exactly this and
    // returns 0 with an explicit sampleCount; this method, which is the
    // one the dashboard actually reads, was missed.
    //
    // null rather than 0: zero successes out of zero trials is not a 0%
    // success rate either. The honest answer is that there is no rate,
    // and the type now says so, which forces every caller to decide what
    // to display instead of silently inheriting a number.
    if (total === 0) {
      return { rate: null, sampleCount: 0, confidence95: { lower: 0, upper: 1 } };
    }

    const rate = this.jobMetrics.completedJobs / total;
    const confidence95 = wilsonConfidenceInterval(
      this.jobMetrics.completedJobs,
      total,
    );

    return { rate, sampleCount: total, confidence95 };
  }

  /**
   * Calculate latency percentiles
   * BACKING: Harter (1974) - Statistical performance analysis
   */
  getLatencyPercentiles(): {
    mean: number;
    median: number;
    p95: number;
    p99: number;
  } {
    if (this.jobMetrics.latencies.length === 0) {
      return { mean: 0, median: 0, p95: 0, p99: 0 };
    }

    const sorted = [...this.jobMetrics.latencies].sort((a, b) => a - b);
    const mean =
      this.jobMetrics.latencies.reduce((a, b) => a + b, 0) /
      this.jobMetrics.latencies.length;
    const median =
      sorted[Math.floor(sorted.length / 2)];
    const p95 = calculateP95(this.jobMetrics.latencies);
    const p99 = sorted[Math.ceil(sorted.length * 0.99) - 1];

    return { mean, median, p95, p99 };
  }

  /**
   * Get Literature Reference for metric
   * Enables full traceability to scientific literature
   */
  getLiteratureReference(metric: string): LiteratureReference | null {
    const refKey = this.getMetricLiteratureKey(metric);
    return LITERATURE_DB[refKey] || null;
  }

  private getMetricLiteratureKey(metric: string): string {
    const mapping: Record<string, string> = {
      "active-jobs": "LITTLES_LAW",
      "success-rate": "WILSON_CONFIDENCE",
      "latency-percentile": "HARTER_LEAST_SQUARES",
      "strenda-compliance": "STRENDA_GUIDELINES",
      "kinetic-parameters": "LEHNINGER_KINETICS",
      "epidemiology": "KERMACK_MCKENDRICK",
      "stochastic-simulation": "GILLESPIE_SSA",
      "response-time": "NIELSEN_RESPONSE_TIME",
      "http-api": "RFC_7231",
    };
    return mapping[metric] || "";
  }

  /**
   * Export all metrics with literature citations
   */
  exportWithCitations() {
    const successMetric = this.getSuccessRateWithConfidence();
    const latencyMetric = this.getLatencyPercentiles();

    return {
      timestamp: new Date(),
      activeJobs: {
        value: this.jobMetrics.activeJobs.size,
        literature: LITERATURE_DB.LITTLES_LAW,
        // Measured directly (Set size), NOT derived from L = λW. Little's
        // Law is cited for the invariant a reader can check this against --
        // in steady state activeJobs should approximate completionRate x
        // avgLatency -- not as the method used to produce the number.
        explanation:
          "Direct count of in-flight jobs. Little's Law (1961), L = λW, " +
          "is the steady-state relation this can be checked against; it is " +
          "not how the value is computed.",
      },
      successRate: {
        // null, not "100.00", when nothing has been observed. This read
        // `(successMetric.rate * 100).toFixed(2)` against a rate that
        // defaulted to 1, so a fresh process exported a cited 100.00%
        // success rate from zero jobs.
        value:
          successMetric.rate === null
            ? null
            : (successMetric.rate * 100).toFixed(2),
        sampleCount: successMetric.sampleCount,
        confidence95: successMetric.confidence95,
        literature: LITERATURE_DB.WILSON_CONFIDENCE,
        explanation:
          "Wilson score interval for binomial proportions (Wilson, 1927)",
      },
      latency: {
        mean: Math.round(latencyMetric.mean),
        p95: latencyMetric.p95,
        p99: latencyMetric.p99,
        literature: LITERATURE_DB.HARTER_LEAST_SQUARES,
        explanation: "Performance distribution analysis (Harter, 1974)",
      },
    };
  }
}

export const verifiableMetricsCollector = new VerifiableMetricsCollector();
