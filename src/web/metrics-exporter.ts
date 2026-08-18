/**
 * Prometheus Metrics Exporter
 *
 * Exports metrics in Prometheus text format for scraping by Prometheus/Grafana
 * Endpoint: GET /metrics
 */

import { getMetricsCollector } from '../storage/metrics-collector';
import { getAllSweepMetrics, getAllBatchMetrics } from '../storage/sweep-batch-metrics';

/**
 * Generate metrics in Prometheus text format
 * https://github.com/prometheus/docs/blob/main/content/docs/instrumenting/exposition_formats.md
 */
export function generatePrometheusMetrics(): string {
  const metrics = getMetricsCollector();
  const agg = metrics.getAggregatedMetrics();
  const byModel = metrics.getMetricsByModel();

  const lines: string[] = [];
  const timestamp = Date.now();

  // HELP and TYPE declarations
  lines.push('# HELP terrium_jobs_total Total number of jobs');
  lines.push('# TYPE terrium_jobs_total gauge');
  lines.push(`terrium_jobs_total ${agg.totalJobs} ${timestamp}`);

  lines.push('# HELP terrium_jobs_successful Successful jobs');
  lines.push('# TYPE terrium_jobs_successful gauge');
  lines.push(`terrium_jobs_successful ${agg.successfulJobs} ${timestamp}`);

  lines.push('# HELP terrium_jobs_failed Failed jobs');
  lines.push('# TYPE terrium_jobs_failed gauge');
  lines.push(`terrium_jobs_failed ${agg.failedJobs} ${timestamp}`);

  // successRate is null only when zero jobs have run at all (as opposed
  // to 0, which is a real "ran jobs, all failed" measurement). Prometheus
  // convention for "no data" is to omit the series, not emit the literal
  // string "null" as a gauge value -- which would not parse as a number
  // and could break a scraping client.
  if (agg.successRate !== null) {
    lines.push('# HELP terrium_success_rate Success rate percentage');
    lines.push('# TYPE terrium_success_rate gauge');
    lines.push(`terrium_success_rate ${agg.successRate} ${timestamp}`);
  }

  // terrium_execution_time_ms_sum/_count: agg.averageExecutionTimeMs is
  // null exactly when agg.successfulJobs is 0 (see metrics-collector.ts),
  // so `avgTime * agg.successfulJobs` is always 0 in that case regardless
  // of the ?? 0 substitution -- sum=0, count=0 is the valid Prometheus
  // summary convention for "no observations", not a fabrication. Safe.
  lines.push('# HELP terrium_execution_time_ms Execution time in milliseconds');
  lines.push('# TYPE terrium_execution_time_ms summary');
  const avgTime = agg.averageExecutionTimeMs ?? 0;
  lines.push(`terrium_execution_time_ms_sum ${avgTime * agg.successfulJobs} ${timestamp}`);
  lines.push(`terrium_execution_time_ms_count ${agg.successfulJobs} ${timestamp}`);

  // The six gauges below (unlike the sum/count pair above) have no such
  // safety net: printing 0 for a null aggregate claims "measured, and it
  // was 0" for a value that was never measured at all -- the same
  // fabricated-zero shape as the old (pre-fix) terrium_success_rate.
  // Omit the series instead, matching terrium_success_rate below and
  // Prometheus convention for missing data.
  if (agg.averageExecutionTimeMs !== null) {
    lines.push('# HELP terrium_execution_time_avg_ms Average execution time');
    lines.push('# TYPE terrium_execution_time_avg_ms gauge');
    lines.push(`terrium_execution_time_avg_ms ${agg.averageExecutionTimeMs} ${timestamp}`);
  }

  if (agg.medianExecutionTimeMs !== null) {
    lines.push('# HELP terrium_execution_time_median_ms Median execution time');
    lines.push('# TYPE terrium_execution_time_median_ms gauge');
    lines.push(`terrium_execution_time_median_ms ${agg.medianExecutionTimeMs} ${timestamp}`);
  }

  if (agg.minExecutionTimeMs !== null) {
    lines.push('# HELP terrium_execution_time_min_ms Minimum execution time');
    lines.push('# TYPE terrium_execution_time_min_ms gauge');
    lines.push(`terrium_execution_time_min_ms ${agg.minExecutionTimeMs} ${timestamp}`);
  }

  if (agg.maxExecutionTimeMs !== null) {
    lines.push('# HELP terrium_execution_time_max_ms Maximum execution time');
    lines.push('# TYPE terrium_execution_time_max_ms gauge');
    lines.push(`terrium_execution_time_max_ms ${agg.maxExecutionTimeMs} ${timestamp}`);
  }

  if (agg.stdDevExecutionTimeMs !== null) {
    lines.push('# HELP terrium_execution_time_stddev_ms Standard deviation of execution time');
    lines.push('# TYPE terrium_execution_time_stddev_ms gauge');
    lines.push(`terrium_execution_time_stddev_ms ${agg.stdDevExecutionTimeMs} ${timestamp}`);
  }

  if (agg.averageConvergenceSteps !== null) {
    lines.push('# HELP terrium_convergence_steps_avg Average convergence steps');
    lines.push('# TYPE terrium_convergence_steps_avg gauge');
    lines.push(`terrium_convergence_steps_avg ${agg.averageConvergenceSteps} ${timestamp}`);
  }

  // Per-model metrics
  lines.push('# HELP terrium_model_jobs_total Jobs per model');
  lines.push('# TYPE terrium_model_jobs_total gauge');
  for (const model of byModel) {
    const safeName = model.query.replace(/-/g, '_');
    lines.push(`terrium_model_jobs_total{model="${model.query}"} ${model.jobCount} ${timestamp}`);
  }

  // ModelMetrics.averageExecutionTimeMs is null for a query where every
  // recorded job failed (no successful execution to time) -- omit that
  // model's series rather than reporting a fabricated 0ms average.
  lines.push('# HELP terrium_model_execution_time_avg_ms Average execution time per model');
  lines.push('# TYPE terrium_model_execution_time_avg_ms gauge');
  for (const model of byModel) {
    if (model.averageExecutionTimeMs !== null) {
      lines.push(`terrium_model_execution_time_avg_ms{model="${model.query}"} ${model.averageExecutionTimeMs} ${timestamp}`);
    }
  }

  // ModelMetrics.successRate is a plain number (never null) -- an
  // all-failed query is reported with successRate: 0, a real measurement,
  // not "no data". No null-omission needed here.
  lines.push('# HELP terrium_model_success_rate Success rate per model');
  lines.push('# TYPE terrium_model_success_rate gauge');
  for (const model of byModel) {
    lines.push(`terrium_model_success_rate{model="${model.query}"} ${model.successRate} ${timestamp}`);
  }

  // ModelMetrics.averageConvergenceSteps is null for the same all-failed
  // reason as averageExecutionTimeMs above.
  lines.push('# HELP terrium_model_convergence_steps_avg Convergence steps per model');
  lines.push('# TYPE terrium_model_convergence_steps_avg gauge');
  for (const model of byModel) {
    if (model.averageConvergenceSteps !== null) {
      lines.push(`terrium_model_convergence_steps_avg{model="${model.query}"} ${model.averageConvergenceSteps} ${timestamp}`);
    }
  }

  // Percentile metrics
  lines.push('# HELP terrium_execution_time_percentile_ms Execution time percentiles');
  lines.push('# TYPE terrium_execution_time_percentile_ms gauge');
  for (const p of [50, 75, 90, 95, 99]) {
    const value = metrics.getPercentile(p);
    // null (no successful execution to compute a percentile from) is
    // omitted rather than printed -- an emitted "null" is not a valid
    // Prometheus sample value.
    if (value !== null) {
      lines.push(`terrium_execution_time_percentile_ms{percentile="${p}"} ${value} ${timestamp}`);
    }
  }

  // Slow queries
  const slowQueries = metrics.getSlowQueries(1000);
  lines.push('# HELP terrium_slow_queries_total Number of slow queries (>1s)');
  lines.push('# TYPE terrium_slow_queries_total gauge');
  lines.push(`terrium_slow_queries_total ${slowQueries.length} ${timestamp}`);

  // Failed queries
  const failedQueries = metrics.getFailedQueries();
  lines.push('# HELP terrium_failed_queries_total Number of failed queries');
  lines.push('# TYPE terrium_failed_queries_total gauge');
  lines.push(`terrium_failed_queries_total ${failedQueries.length} ${timestamp}`);

  // Sweep metrics
  const sweepMetrics = getAllSweepMetrics();
  lines.push('# HELP terrium_sweeps_total Total number of sweeps');
  lines.push('# TYPE terrium_sweeps_total gauge');
  lines.push(`terrium_sweeps_total ${sweepMetrics.length} ${timestamp}`);

  // SweepMetrics.successRate/averageTimeMs are null only for a sweep
  // recorded with zero simulations (not reachable via the real
  // /api/sweep path today, see sweep-batch-metrics.ts, but the type is
  // honest about it). Excluded from the average rather than counted as
  // 0, same reasoning as agg.successRate above.
  const sweepsWithRate = sweepMetrics.filter((m): m is typeof m & { successRate: number } => m.successRate !== null);
  const sweepsWithTime = sweepMetrics.filter((m): m is typeof m & { averageTimeMs: number } => m.averageTimeMs !== null);

  if (sweepsWithRate.length > 0) {
    lines.push('# HELP terrium_sweep_avg_success_rate Average success rate across sweeps');
    lines.push('# TYPE terrium_sweep_avg_success_rate gauge');
    const avgSweepSuccess = sweepsWithRate.reduce((a, b) => a + b.successRate, 0) / sweepsWithRate.length;
    lines.push(`terrium_sweep_avg_success_rate ${avgSweepSuccess} ${timestamp}`);
  }

  if (sweepsWithTime.length > 0) {
    lines.push('# HELP terrium_sweep_avg_execution_time_ms Average execution time per sweep');
    lines.push('# TYPE terrium_sweep_avg_execution_time_ms gauge');
    const avgSweepTime = sweepsWithTime.reduce((a, b) => a + b.averageTimeMs, 0) / sweepsWithTime.length;
    lines.push(`terrium_sweep_avg_execution_time_ms ${avgSweepTime} ${timestamp}`);
  }

  // Batch metrics
  const batchMetrics = getAllBatchMetrics();
  lines.push('# HELP terrium_batches_total Total number of batch operations');
  lines.push('# TYPE terrium_batches_total gauge');
  lines.push(`terrium_batches_total ${batchMetrics.length} ${timestamp}`);

  // Same null-only-for-zero-jobs reasoning as sweeps above.
  const batchesWithRate = batchMetrics.filter((m): m is typeof m & { successRate: number } => m.successRate !== null);
  const batchesWithTime = batchMetrics.filter((m): m is typeof m & { averageTimeMs: number } => m.averageTimeMs !== null);

  if (batchesWithRate.length > 0) {
    lines.push('# HELP terrium_batch_avg_success_rate Average success rate across batches');
    lines.push('# TYPE terrium_batch_avg_success_rate gauge');
    const avgBatchSuccess = batchesWithRate.reduce((a, b) => a + b.successRate, 0) / batchesWithRate.length;
    lines.push(`terrium_batch_avg_success_rate ${avgBatchSuccess} ${timestamp}`);
  }

  if (batchesWithTime.length > 0) {
    lines.push('# HELP terrium_batch_avg_execution_time_ms Average execution time per batch');
    lines.push('# TYPE terrium_batch_avg_execution_time_ms gauge');
    const avgBatchTime = batchesWithTime.reduce((a, b) => a + b.averageTimeMs, 0) / batchesWithTime.length;
    lines.push(`terrium_batch_avg_execution_time_ms ${avgBatchTime} ${timestamp}`);
  }

  return lines.join('\n') + '\n';
}
