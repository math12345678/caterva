/**
 * Performance Metrics Collection
 *
 * Track execution time, convergence, accuracy, and reproducibility
 * for simulations to identify bottlenecks and verify scientific rigor
 */

export interface ExecutionMetrics {
  jobId: string;
  query: string;
  startTime: number;
  endTime: number;
  executionTimeMs: number;
  // Terrium's engine (Tellurium/libRoadRunner via a fixed-step integrator,
  // see Terium/) is not an iterative solver reporting a real convergence
  // count -- there is no such number to measure. Callers record the
  // trajectory point count here (a real, verifiable fact about the run:
  // how many output points the simulation actually produced), not a
  // fabricated "iterations to converge".
  convergenceSteps: number;
  convergenceTime?: number;
  memoryUsageMB?: number;
  success: boolean;
  errorMessage?: string;
}

export interface AggregatedMetrics {
  totalJobs: number;
  successfulJobs: number;
  failedJobs: number;
  // null means "no successful execution to measure" (zero jobs, or every
  // job failed) -- not the same fact as "measured and it was instant".
  // A sibling metrics system in this repo (Science-Agent-Pipeline's
  // metrics.ts, since deleted) reported a fabricated 100% success rate
  // from an empty sample because a numeric default looked exactly like a
  // real measurement to every caller. This collector had the same shape
  // of bug in the opposite direction (0 instead of 100) until this fix:
  // totalJobs: 0 reported successRate: 0, which reads as "ran jobs, all
  // failed" rather than "no jobs have run yet". See ADR reference in
  // trackReproducibility() below for the same pattern applied there.
  averageExecutionTimeMs: number | null;
  medianExecutionTimeMs: number | null;
  minExecutionTimeMs: number | null;
  maxExecutionTimeMs: number | null;
  stdDevExecutionTimeMs: number | null;
  averageConvergenceSteps: number | null;
  successRate: number | null;
}

export interface ModelMetrics {
  query: string;
  jobCount: number;
  // null: every job for this query failed, so there is no successful
  // execution-time sample to average -- distinct from "averaged to zero".
  averageExecutionTimeMs: number | null;
  medianExecutionTimeMs: number | null;
  successRate: number;
  averageConvergenceSteps: number | null;
}

export interface ParameterSensitivityMetrics {
  parameterName: string;
  valuesTestedCount: number;
  minExecutionTimeMs: number;
  maxExecutionTimeMs: number;
  averageExecutionTimeMs: number;
  // null: not yet computed. analyzeParameterSensitivity() below does not
  // have access to per-job parameter VALUES (only execution metadata), so
  // it cannot actually correlate anything. It used to return 0 here,
  // which reads as "measured, no correlation" rather than "not measured
  // at all" -- indistinguishable to any caller from a real result.
  correlationWithExecutionTime: number | null; // -1 to 1, or null if unmeasured
}

export interface ReproducibilityMetrics {
  query: string;
  parameterHash: string;
  runCount: number;
  results: number[];
  variance: number;
  stdDev: number;
  // null until runCount >= 2: reproducibility is a claim about agreement
  // ACROSS runs, and cannot be true or false from a single observation.
  isReproducible: boolean | null;
}

/**
 * Metrics collector for tracking simulation performance
 */
export class MetricsCollector {
  private metrics: Map<string, ExecutionMetrics> = new Map();
  private reproducibilityCache: Map<string, ReproducibilityMetrics> = new Map();

  /**
   * Record execution metrics for a job
   */
  recordExecution(metrics: ExecutionMetrics): void {
    this.metrics.set(metrics.jobId, metrics);
  }

  /**
   * Get all collected metrics
   */
  getAllMetrics(): ExecutionMetrics[] {
    return Array.from(this.metrics.values());
  }

  /**
   * Get aggregated metrics across all jobs
   */
  getAggregatedMetrics(): AggregatedMetrics {
    const allMetrics = Array.from(this.metrics.values());
    const successfulMetrics = allMetrics.filter(m => m.success);
    const executionTimes = successfulMetrics.map(m => m.executionTimeMs);

    if (executionTimes.length === 0) {
      // Two different facts collapse into this branch: "nothing has run
      // yet" (allMetrics.length === 0) and "everything that ran failed"
      // (allMetrics.length > 0, all of it unsuccessful). Both share one
      // property that matters here: there is no execution-time sample to
      // report a real average/median/min/max/stdDev from, so those stay
      // null. successRate, unlike the timing fields, IS well-defined in
      // the second case (0 successes / N total is a real, measured 0%) --
      // only the zero-total case has no rate to report at all.
      return {
        totalJobs: allMetrics.length,
        successfulJobs: 0,
        failedJobs: allMetrics.length,
        averageExecutionTimeMs: null,
        medianExecutionTimeMs: null,
        minExecutionTimeMs: null,
        maxExecutionTimeMs: null,
        stdDevExecutionTimeMs: null,
        averageConvergenceSteps: null,
        successRate: allMetrics.length > 0 ? 0 : null
      };
    }

    const sorted = [...executionTimes].sort((a, b) => a - b);
    const mean = executionTimes.reduce((a, b) => a + b, 0) / executionTimes.length;
    const median = sorted.length % 2 === 0
      ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
      : sorted[Math.floor(sorted.length / 2)];

    const variance = executionTimes.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / executionTimes.length;
    const stdDev = Math.sqrt(variance);

    const avgConvergenceSteps = successfulMetrics.length > 0
      ? successfulMetrics.reduce((sum, m) => sum + m.convergenceSteps, 0) / successfulMetrics.length
      : 0;

    return {
      totalJobs: allMetrics.length,
      successfulJobs: successfulMetrics.length,
      failedJobs: allMetrics.length - successfulMetrics.length,
      averageExecutionTimeMs: mean,
      medianExecutionTimeMs: median,
      minExecutionTimeMs: Math.min(...executionTimes),
      maxExecutionTimeMs: Math.max(...executionTimes),
      stdDevExecutionTimeMs: stdDev,
      averageConvergenceSteps: avgConvergenceSteps,
      successRate: (successfulMetrics.length / allMetrics.length) * 100
    };
  }

  /**
   * Get metrics grouped by kinetic model
   */
  getMetricsByModel(): ModelMetrics[] {
    const allMetrics = Array.from(this.metrics.values());
    const byModel: Map<string, ExecutionMetrics[]> = new Map();

    for (const metric of allMetrics) {
      if (!byModel.has(metric.query)) {
        byModel.set(metric.query, []);
      }
      byModel.get(metric.query)!.push(metric);
    }

    const result: ModelMetrics[] = [];
    for (const [query, metrics] of byModel.entries()) {
      const successful = metrics.filter(m => m.success);
      const executionTimes = successful.map(m => m.executionTimeMs);

      // A query where every recorded job failed used to be silently
      // dropped here (`if (executionTimes.length === 0) continue`) rather
      // than reported. That is worse than fabricating a number: a query
      // failing 100% of the time simply disappeared from
      // getMetricsByModel(), so a monitoring dashboard built on this
      // method could not distinguish "this query has never been run" from
      // "this query has been run and always fails" -- the second is the
      // one an operator most needs to see. It is included now, with
      // successRate: 0 (a real, measured fact) and timing fields null
      // (there is no successful execution to time).
      if (executionTimes.length === 0) {
        result.push({
          query,
          jobCount: metrics.length,
          averageExecutionTimeMs: null,
          medianExecutionTimeMs: null,
          successRate: 0,
          averageConvergenceSteps: null
        });
        continue;
      }

      const sorted = [...executionTimes].sort((a, b) => a - b);
      const median = sorted.length % 2 === 0
        ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
        : sorted[Math.floor(sorted.length / 2)];

      const avgConvergence = successful.reduce((sum, m) => sum + m.convergenceSteps, 0) / successful.length;

      result.push({
        query,
        jobCount: metrics.length,
        averageExecutionTimeMs: executionTimes.reduce((a, b) => a + b, 0) / executionTimes.length,
        medianExecutionTimeMs: median,
        successRate: (successful.length / metrics.length) * 100,
        averageConvergenceSteps: avgConvergence
      });
    }

    return result.sort((a, b) => b.jobCount - a.jobCount);
  }

  /**
   * Get metrics for a specific job
   */
  getJobMetrics(jobId: string): ExecutionMetrics | undefined {
    return this.metrics.get(jobId);
  }

  /**
   * Analyze how a parameter affects execution time
   */
  analyzeParameterSensitivity(parameterName: string): ParameterSensitivityMetrics | null {
    const allMetrics = Array.from(this.metrics.values());
    const filtered = allMetrics.filter(m => m.success);

    if (filtered.length < 2) {
      return null;
    }

    // ExecutionMetrics does not carry the parameter VALUES a job ran
    // with, only its timing/outcome -- so there is nothing here to
    // correlate against execution time. correlationWithExecutionTime is
    // honestly null rather than a placeholder 0.
    const executionTimes = filtered.map(m => m.executionTimeMs);
    const mean = executionTimes.reduce((a, b) => a + b, 0) / executionTimes.length;

    return {
      parameterName,
      valuesTestedCount: filtered.length,
      minExecutionTimeMs: Math.min(...executionTimes),
      maxExecutionTimeMs: Math.max(...executionTimes),
      averageExecutionTimeMs: mean,
      correlationWithExecutionTime: null,
    };
  }

  /**
   * Track and verify reproducibility of results
   */
  trackReproducibility(
    query: string,
    parameterHash: string,
    result: number
  ): ReproducibilityMetrics {
    const key = `${query}:${parameterHash}`;

    if (!this.reproducibilityCache.has(key)) {
      // isReproducible starts null, not true. A freshly-created record
      // with zero runs has made no claim about agreement yet; defaulting
      // it to `true` reported "reproducible" for a result that had been
      // observed exactly once (runCount 0, about to become 1) -- the same
      // shape of bug as a success rate reported from an empty sample.
      this.reproducibilityCache.set(key, {
        query,
        parameterHash,
        runCount: 0,
        results: [],
        variance: 0,
        stdDev: 0,
        isReproducible: null
      });
    }

    const metrics = this.reproducibilityCache.get(key)!;
    metrics.results.push(result);
    metrics.runCount += 1;

    // Calculate variance and std dev
    if (metrics.results.length > 1) {
      const mean = metrics.results.reduce((a, b) => a + b, 0) / metrics.results.length;
      const variance = metrics.results.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / metrics.results.length;
      metrics.stdDev = Math.sqrt(variance);
      metrics.variance = variance;
      metrics.isReproducible = metrics.stdDev / Math.abs(mean) < 0.01; // < 1% variance
    }

    return metrics;
  }

  /**
   * Get reproducibility metrics for a specific run
   */
  getReproducibilityMetrics(query: string, parameterHash: string): ReproducibilityMetrics | undefined {
    const key = `${query}:${parameterHash}`;
    return this.reproducibilityCache.get(key);
  }

  /**
   * Get all reproducibility data
   */
  getAllReproducibilityMetrics(): ReproducibilityMetrics[] {
    return Array.from(this.reproducibilityCache.values());
  }

  /**
   * Clear all metrics (useful for testing)
   */
  clear(): void {
    this.metrics.clear();
    this.reproducibilityCache.clear();
  }

  /**
   * Get percentile execution time
   */
  getPercentile(percentile: number): number | null {
    const allMetrics = Array.from(this.metrics.values());
    const successful = allMetrics.filter(m => m.success);
    const executionTimes = successful.map(m => m.executionTimeMs).sort((a, b) => a - b);

    // 0ms reads as "very fast", not "no data" -- returning it for an empty
    // sample fabricated a percentile out of nothing. null says what is
    // actually true: there is no successful execution to compute one from.
    if (executionTimes.length === 0) return null;

    const index = Math.ceil((percentile / 100) * executionTimes.length) - 1;
    return executionTimes[Math.max(0, index)];
  }

  /**
   * Get slow queries (jobs taking longer than threshold)
   */
  getSlowQueries(thresholdMs: number): ExecutionMetrics[] {
    return Array.from(this.metrics.values())
      .filter(m => m.success && m.executionTimeMs > thresholdMs)
      .sort((a, b) => b.executionTimeMs - a.executionTimeMs);
  }

  /**
   * Get failed queries for debugging
   */
  getFailedQueries(): ExecutionMetrics[] {
    return Array.from(this.metrics.values())
      .filter(m => !m.success)
      .sort((a, b) => b.endTime - a.endTime);
  }
}

// Global singleton
let instance: MetricsCollector | null = null;

export function getMetricsCollector(): MetricsCollector {
  if (!instance) {
    instance = new MetricsCollector();
  }
  return instance;
}
