/**
 * Metrics Collection System
 * Tracks pipeline performance across all 5 stages and all 13 domains
 * Exports data for dashboard visualization and monitoring
 */

import { logger } from "./logger";

export interface StageMetrics {
  name: string;
  successCount: number;
  failureCount: number;
  avgDurationMs: number;
  samples: number[];
}

export interface DomainMetrics {
  domain: string;
  count: number;
  avgResolutionMs: number;
  parameterSuccessRate: number;
  samples: number[];
}

export interface ResolutionMetrics {
  llmClassificationSuccesses: number;
  llmClassificationFailures: number;
  keywordFallbackUsed: number;
  literatureHitCount: number;
  literatureMissCount: number;
}

export interface PipelineMetrics {
  timestamp: Date;
  activeJobs: number;
  completedJobs: number;
  failedJobs: number;
  avgLatencyMs: number;
  stageMetrics: Record<string, StageMetrics>;
  domainMetrics: Record<string, DomainMetrics>;
  resolutionMetrics: ResolutionMetrics;
  llmSuccessRate: number;
  literatureHitRate: number;
}

const STAGE_NAMES = [
  "Entity Extraction",
  "Parameter Resolution",
  "Domain Classification",
  "Validation",
  "Simulation Output",
];

const DOMAINS = [
  "mm",
  "mm_competitive_inhibition",
  "sir",
  "seir",
  "pcr",
  "monte_carlo_pi",
  "wright_fisher",
  "two_locus_wright_fisher",
  "molecular_dynamics",
  "gillespie_ssa",
  "gillespie_ssa_bimolecular",
  "gillespie_ssa_replicates",
];

/**
 * Metrics collection singleton that tracks pipeline performance
 * Maintains a rolling window of recent metrics for dashboard export
 */
class MetricsCollector {
  private stageMetrics: Record<string, StageMetrics> = {};
  private domainMetrics: Record<string, DomainMetrics> = {};
  private resolutionMetrics: ResolutionMetrics;

  private activeJobs: Set<string> = new Set();
  private completedJobs: number = 0;
  private failedJobs: number = 0;
  private jobLatencies: number[] = [];

  private maxSamples: number = 100; // Keep last 100 samples per metric

  constructor() {
    this.resolutionMetrics = {
      llmClassificationSuccesses: 0,
      llmClassificationFailures: 0,
      keywordFallbackUsed: 0,
      literatureHitCount: 0,
      literatureMissCount: 0,
    };

    // Initialize stage metrics
    for (const stage of STAGE_NAMES) {
      this.stageMetrics[stage] = {
        name: stage,
        successCount: 0,
        failureCount: 0,
        avgDurationMs: 0,
        samples: [],
      };
    }

    // Initialize domain metrics
    for (const domain of DOMAINS) {
      this.domainMetrics[domain] = {
        domain,
        count: 0,
        avgResolutionMs: 0,
        parameterSuccessRate: 0,
        samples: [],
      };
    }
  }

  /**
   * Record a job as started
   */
  recordJobStart(jobId: string): void {
    this.activeJobs.add(jobId);
  }

  /**
   * Record a job as completed with latency
   */
  recordJobCompletion(jobId: string, latencyMs: number): void {
    this.activeJobs.delete(jobId);
    this.completedJobs++;
    this.jobLatencies.push(latencyMs);

    // Keep only last 100 latencies
    if (this.jobLatencies.length > this.maxSamples) {
      this.jobLatencies.shift();
    }
  }

  /**
   * Record a job failure
   */
  recordJobFailure(jobId: string): void {
    this.activeJobs.delete(jobId);
    this.failedJobs++;
  }

  /**
   * Record stage execution metrics
   */
  recordStageExecution(
    stageName: string,
    durationMs: number,
    success: boolean,
  ): void {
    const stage = this.stageMetrics[stageName];
    if (!stage) {
      logger.warn({ stageName }, "Unknown stage in metrics");
      return;
    }

    if (success) {
      stage.successCount++;
    } else {
      stage.failureCount++;
    }

    stage.samples.push(durationMs);
    if (stage.samples.length > this.maxSamples) {
      stage.samples.shift();
    }

    // Update running average
    if (stage.samples.length > 0) {
      stage.avgDurationMs =
        stage.samples.reduce((a, b) => a + b, 0) / stage.samples.length;
    }
  }

  /**
   * Record domain usage
   */
  recordDomainUsage(
    domain: string,
    resolutionMs: number,
    parameterSuccess: boolean,
  ): void {
    const domainMetric = this.domainMetrics[domain];
    if (!domainMetric) {
      logger.warn({ domain }, "Unknown domain in metrics");
      return;
    }

    domainMetric.count++;
    domainMetric.samples.push(resolutionMs);

    if (domainMetric.samples.length > this.maxSamples) {
      domainMetric.samples.shift();
    }

    // Update running average
    if (domainMetric.samples.length > 0) {
      domainMetric.avgResolutionMs =
        domainMetric.samples.reduce((a, b) => a + b, 0) /
        domainMetric.samples.length;
    }

    // Update parameter success rate
    const totalInWindow = Math.min(20, domainMetric.count); // Rolling window of last 20
    if (parameterSuccess) {
      domainMetric.parameterSuccessRate =
        (domainMetric.parameterSuccessRate * (totalInWindow - 1) + 100) /
        totalInWindow;
    } else {
      domainMetric.parameterSuccessRate =
        (domainMetric.parameterSuccessRate * (totalInWindow - 1) + 0) /
        totalInWindow;
    }
  }

  /**
   * Record LLM classification result
   */
  recordLLMClassification(success: boolean): void {
    if (success) {
      this.resolutionMetrics.llmClassificationSuccesses++;
    } else {
      this.resolutionMetrics.llmClassificationFailures++;
    }
  }

  /**
   * Record fallback to keyword matching
   */
  recordKeywordFallback(): void {
    this.resolutionMetrics.keywordFallbackUsed++;
  }

  /**
   * Record literature resolution result
   */
  recordLiteratureResolution(hit: boolean): void {
    if (hit) {
      this.resolutionMetrics.literatureHitCount++;
    } else {
      this.resolutionMetrics.literatureMissCount++;
    }
  }

  /**
   * Get current snapshot of all metrics
   */
  getSnapshot(): PipelineMetrics {
    const totalLLMAttempts =
      this.resolutionMetrics.llmClassificationSuccesses +
      this.resolutionMetrics.llmClassificationFailures;

    const llmSuccessRate =
      totalLLMAttempts > 0
        ? (this.resolutionMetrics.llmClassificationSuccesses / totalLLMAttempts) *
          100
        : 100;

    const totalLiteratureAttempts =
      this.resolutionMetrics.literatureHitCount +
      this.resolutionMetrics.literatureMissCount;

    const literatureHitRate =
      totalLiteratureAttempts > 0
        ? (this.resolutionMetrics.literatureHitCount / totalLiteratureAttempts) *
          100
        : 100;

    const avgLatencyMs =
      this.jobLatencies.length > 0
        ? this.jobLatencies.reduce((a, b) => a + b, 0) / this.jobLatencies.length
        : 0;

    return {
      timestamp: new Date(),
      activeJobs: this.activeJobs.size,
      completedJobs: this.completedJobs,
      failedJobs: this.failedJobs,
      avgLatencyMs,
      stageMetrics: this.stageMetrics,
      domainMetrics: this.domainMetrics,
      resolutionMetrics: { ...this.resolutionMetrics },
      llmSuccessRate,
      literatureHitRate,
    };
  }

  /**
   * Reset all metrics (useful for testing or production restarts)
   */
  reset(): void {
    this.activeJobs.clear();
    this.completedJobs = 0;
    this.failedJobs = 0;
    this.jobLatencies = [];

    for (const stage of STAGE_NAMES) {
      this.stageMetrics[stage] = {
        name: stage,
        successCount: 0,
        failureCount: 0,
        avgDurationMs: 0,
        samples: [],
      };
    }

    for (const domain of DOMAINS) {
      this.domainMetrics[domain] = {
        domain,
        count: 0,
        avgResolutionMs: 0,
        parameterSuccessRate: 0,
        samples: [],
      };
    }

    this.resolutionMetrics = {
      llmClassificationSuccesses: 0,
      llmClassificationFailures: 0,
      keywordFallbackUsed: 0,
      literatureHitCount: 0,
      literatureMissCount: 0,
    };

    logger.info("Metrics collector reset");
  }

  /**
   * Export metrics as JSON for API endpoint
   */
  toJSON() {
    return this.getSnapshot();
  }
}

// Singleton instance
const metricsCollector = new MetricsCollector();

export { metricsCollector };

/**
 * Helper function to record a complete job execution
 * Convenience wrapper around multiple metric recording calls
 */
export function recordJobExecution(
  jobId: string,
  domain: string,
  latencyMs: number,
  success: boolean,
  stageTimings: Record<string, { duration: number; success: boolean }>,
  llmUsed: boolean,
  llmSuccess: boolean,
  literatureHit: boolean,
): void {
  if (success) {
    metricsCollector.recordJobCompletion(jobId, latencyMs);
  } else {
    metricsCollector.recordJobFailure(jobId);
  }

  // Record stage metrics
  for (const [stageName, { duration, success: stageSuccess }] of Object.entries(
    stageTimings,
  )) {
    metricsCollector.recordStageExecution(stageName, duration, stageSuccess);
  }

  // Record domain usage
  metricsCollector.recordDomainUsage(domain, latencyMs, success);

  // Record resolution metrics
  if (llmUsed) {
    metricsCollector.recordLLMClassification(llmSuccess);
  }

  if (!llmUsed && llmSuccess === false) {
    // Keyword fallback was used
    metricsCollector.recordKeywordFallback();
  }

  metricsCollector.recordLiteratureResolution(literatureHit);
}
