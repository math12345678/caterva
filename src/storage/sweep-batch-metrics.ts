/**
 * Sweep and Batch Metrics Tracking
 *
 * Records metrics for parameter sweep and batch operations
 * in addition to individual simulations
 */

import { getMetricsCollector } from './metrics-collector';

export interface SweepMetrics {
  sweepId: string;
  query: string;
  totalSimulations: number;
  completedSimulations: number;
  successfulSimulations: number;
  failedSimulations: number;
  totalTimeMs: number;
  // null only when `results` was empty (zero simulations recorded) --
  // not reachable through the real /api/sweep path today because
  // validateSweepRequest() requires at least one sweep parameter and
  // generateSweepPoints() always yields >=1 point for a valid min<max
  // range (see parameter-sweep.ts), but recordSweepMetrics() is an
  // exported function any future caller could still invoke with an
  // empty array. These used to default to 0, which reads as "measured,
  // instant/all-failed" rather than "no simulations to measure" -- the
  // same fabricated-zero shape already fixed in metrics-collector.ts.
  averageTimeMs: number | null;
  minTimeMs: number | null;
  maxTimeMs: number | null;
  successRate: number | null;
}

export interface BatchMetrics {
  batchId: string;
  query: string;
  totalJobs: number;
  completedJobs: number;
  successfulJobs: number;
  failedJobs: number;
  totalTimeMs: number;
  // See SweepMetrics above: null only for zero recorded jobs, not
  // reachable via the real /api/batch path (validateBatchRequest()
  // requires at least one parameter set) but honest for any other
  // caller of recordBatchMetrics().
  averageTimeMs: number | null;
  minTimeMs: number | null;
  maxTimeMs: number | null;
  successRate: number | null;
}

/**
 * Sweep metrics storage (in-memory for session)
 */
const sweepMetricsCache = new Map<string, SweepMetrics>();
const batchMetricsCache = new Map<string, BatchMetrics>();

/**
 * Record a sweep operation's metrics
 */
export function recordSweepMetrics(
  sweepId: string,
  query: string,
  results: Array<{ executionTimeMs: number; validated: boolean }>
): SweepMetrics {
  const successfulCount = results.filter(r => r.validated).length;
  const executionTimes = results.map(r => r.executionTimeMs);

  const metrics: SweepMetrics = {
    sweepId,
    query,
    totalSimulations: results.length,
    completedSimulations: results.length,
    successfulSimulations: successfulCount,
    failedSimulations: results.length - successfulCount,
    totalTimeMs: executionTimes.reduce((a, b) => a + b, 0),
    averageTimeMs: executionTimes.length > 0 ? executionTimes.reduce((a, b) => a + b, 0) / executionTimes.length : null,
    minTimeMs: executionTimes.length > 0 ? Math.min(...executionTimes) : null,
    maxTimeMs: executionTimes.length > 0 ? Math.max(...executionTimes) : null,
    successRate: results.length > 0 ? (successfulCount / results.length) * 100 : null
  };

  sweepMetricsCache.set(sweepId, metrics);
  return metrics;
}

/**
 * Record a batch operation's metrics
 */
export function recordBatchMetrics(
  batchId: string,
  query: string,
  results: Array<{ executionTimeMs: number; validated: boolean }>
): BatchMetrics {
  const successfulCount = results.filter(r => r.validated).length;
  const executionTimes = results.map(r => r.executionTimeMs);

  const metrics: BatchMetrics = {
    batchId,
    query,
    totalJobs: results.length,
    completedJobs: results.length,
    successfulJobs: successfulCount,
    failedJobs: results.length - successfulCount,
    totalTimeMs: executionTimes.reduce((a, b) => a + b, 0),
    averageTimeMs: executionTimes.length > 0 ? executionTimes.reduce((a, b) => a + b, 0) / executionTimes.length : null,
    minTimeMs: executionTimes.length > 0 ? Math.min(...executionTimes) : null,
    maxTimeMs: executionTimes.length > 0 ? Math.max(...executionTimes) : null,
    successRate: results.length > 0 ? (successfulCount / results.length) * 100 : null
  };

  batchMetricsCache.set(batchId, metrics);
  return metrics;
}

/**
 * Record individual job metrics from sweep/batch
 *
 * This allows tracking each simulation within a sweep/batch operation
 *
 * DEAD CODE WARNING: this function is exported and imported by
 * parameter-sweep.ts but is never actually called there (verified by
 * grep across src/ -- there is no call site anywhere in the repo). If a
 * future change wires it up, note that `convergenceSteps: 0` below is a
 * hardcoded placeholder, not a real measurement: ExecutionMetrics.
 * convergenceSteps is documented in metrics-collector.ts as "the
 * trajectory point count... a real, verifiable fact about the run", and
 * this function has no access to that value (its signature only carries
 * executionTimeMs/validated/errorMessage). Wiring this in as-is would
 * silently claim "0 trajectory points" for every sweep job regardless of
 * what actually ran -- the exact fabricated-measurement shape this
 * session's audit was created to catch. Fix by threading the real
 * trajectory length through from the caller before wiring this in, not
 * by leaving the hardcoded 0.
 */
export function recordSweepJobMetrics(
  jobId: string,
  query: string,
  executionTimeMs: number,
  validated: boolean,
  errorMessage?: string
): void {
  const metricsCollector = getMetricsCollector();

  metricsCollector.recordExecution({
    jobId,
    query,
    startTime: Date.now() - executionTimeMs,
    endTime: Date.now(),
    executionTimeMs,
    convergenceSteps: 0, // Sweeps don't track convergence
    success: validated,
    errorMessage
  });
}

/**
 * Get sweep metrics
 */
export function getSweepMetrics(sweepId: string): SweepMetrics | undefined {
  return sweepMetricsCache.get(sweepId);
}

/**
 * Get all sweep metrics
 */
export function getAllSweepMetrics(): SweepMetrics[] {
  return Array.from(sweepMetricsCache.values());
}

/**
 * Get batch metrics
 */
export function getBatchMetrics(batchId: string): BatchMetrics | undefined {
  return batchMetricsCache.get(batchId);
}

/**
 * Get all batch metrics
 */
export function getAllBatchMetrics(): BatchMetrics[] {
  return Array.from(batchMetricsCache.values());
}

/**
 * Aggregate sweep metrics by query
 */
export function getSweepMetricsByQuery(): Map<string, SweepMetrics[]> {
  const byQuery = new Map<string, SweepMetrics[]>();

  for (const metrics of sweepMetricsCache.values()) {
    if (!byQuery.has(metrics.query)) {
      byQuery.set(metrics.query, []);
    }
    byQuery.get(metrics.query)!.push(metrics);
  }

  return byQuery;
}

/**
 * Aggregate batch metrics by query
 */
export function getBatchMetricsByQuery(): Map<string, BatchMetrics[]> {
  const byQuery = new Map<string, BatchMetrics[]>();

  for (const metrics of batchMetricsCache.values()) {
    if (!byQuery.has(metrics.query)) {
      byQuery.set(metrics.query, []);
    }
    byQuery.get(metrics.query)!.push(metrics);
  }

  return byQuery;
}

/**
 * Clear all cached metrics (for testing)
 */
export function clearSweepBatchMetrics(): void {
  sweepMetricsCache.clear();
  batchMetricsCache.clear();
}
