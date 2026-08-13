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

  lines.push('# HELP terrium_execution_time_ms Execution time in milliseconds');
  lines.push('# TYPE terrium_execution_time_ms summary');
  const avgTime = agg.averageExecutionTimeMs ?? 0;
  lines.push(`terrium_execution_time_ms_sum ${avgTime * agg.successfulJobs} ${timestamp}`);
  lines.push(`terrium_execution_time_ms_count ${agg.successfulJobs} ${timestamp}`);

  lines.push('# HELP terrium_execution_time_avg_ms Average execution time');
  lines.push('# TYPE terrium_execution_time_avg_ms gauge');
  lines.push(`terrium_execution_time_avg_ms ${agg.averageExecutionTimeMs ?? 0} ${timestamp}`);

  lines.push('# HELP terrium_execution_time_median_ms Median execution time');
  lines.push('# TYPE terrium_execution_time_median_ms gauge');
  lines.push(`terrium_execution_time_median_ms ${agg.medianExecutionTimeMs ?? 0} ${timestamp}`);

  lines.push('# HELP terrium_execution_time_min_ms Minimum execution time');
  lines.push('# TYPE terrium_execution_time_min_ms gauge');
  lines.push(`terrium_execution_time_min_ms ${agg.minExecutionTimeMs ?? 0} ${timestamp}`);

  lines.push('# HELP terrium_execution_time_max_ms Maximum execution time');
  lines.push('# TYPE terrium_execution_time_max_ms gauge');
  lines.push(`terrium_execution_time_max_ms ${agg.maxExecutionTimeMs ?? 0} ${timestamp}`);

  lines.push('# HELP terrium_execution_time_stddev_ms Standard deviation of execution time');
  lines.push('# TYPE terrium_execution_time_stddev_ms gauge');
  lines.push(`terrium_execution_time_stddev_ms ${agg.stdDevExecutionTimeMs ?? 0} ${timestamp}`);

  lines.push('# HELP terrium_convergence_steps_avg Average convergence steps');
  lines.push('# TYPE terrium_convergence_steps_avg gauge');
  lines.push(`terrium_convergence_steps_avg ${agg.averageConvergenceSteps ?? 0} ${timestamp}`);

  // Per-model metrics
  lines.push('# HELP terrium_model_jobs_total Jobs per model');
  lines.push('# TYPE terrium_model_jobs_total gauge');
  for (const model of byModel) {
    const safeName = model.query.replace(/-/g, '_');
    lines.push(`terrium_model_jobs_total{model="${model.query}"} ${model.jobCount} ${timestamp}`);
  }

  lines.push('# HELP terrium_model_execution_time_avg_ms Average execution time per model');
  lines.push('# TYPE terrium_model_execution_time_avg_ms gauge');
  for (const model of byModel) {
    lines.push(`terrium_model_execution_time_avg_ms{model="${model.query}"} ${model.averageExecutionTimeMs ?? 0} ${timestamp}`);
  }

  lines.push('# HELP terrium_model_success_rate Success rate per model');
  lines.push('# TYPE terrium_model_success_rate gauge');
  for (const model of byModel) {
    lines.push(`terrium_model_success_rate{model="${model.query}"} ${model.successRate ?? 0} ${timestamp}`);
  }

  lines.push('# HELP terrium_model_convergence_steps_avg Convergence steps per model');
  lines.push('# TYPE terrium_model_convergence_steps_avg gauge');
  for (const model of byModel) {
    lines.push(`terrium_model_convergence_steps_avg{model="${model.query}"} ${model.averageConvergenceSteps ?? 0} ${timestamp}`);
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

  if (sweepMetrics.length > 0) {
    lines.push('# HELP terrium_sweep_avg_success_rate Average success rate across sweeps');
    lines.push('# TYPE terrium_sweep_avg_success_rate gauge');
    const avgSweepSuccess = sweepMetrics.reduce((a, b) => a + b.successRate, 0) / sweepMetrics.length;
    lines.push(`terrium_sweep_avg_success_rate ${avgSweepSuccess} ${timestamp}`);

    lines.push('# HELP terrium_sweep_avg_execution_time_ms Average execution time per sweep');
    lines.push('# TYPE terrium_sweep_avg_execution_time_ms gauge');
    const avgSweepTime = sweepMetrics.reduce((a, b) => a + b.averageTimeMs, 0) / sweepMetrics.length;
    lines.push(`terrium_sweep_avg_execution_time_ms ${avgSweepTime ?? 0} ${timestamp}`);
  }

  // Batch metrics
  const batchMetrics = getAllBatchMetrics();
  lines.push('# HELP terrium_batches_total Total number of batch operations');
  lines.push('# TYPE terrium_batches_total gauge');
  lines.push(`terrium_batches_total ${batchMetrics.length} ${timestamp}`);

  if (batchMetrics.length > 0) {
    lines.push('# HELP terrium_batch_avg_success_rate Average success rate across batches');
    lines.push('# TYPE terrium_batch_avg_success_rate gauge');
    const avgBatchSuccess = batchMetrics.reduce((a, b) => a + b.successRate, 0) / batchMetrics.length;
    lines.push(`terrium_batch_avg_success_rate ${avgBatchSuccess} ${timestamp}`);

    lines.push('# HELP terrium_batch_avg_execution_time_ms Average execution time per batch');
    lines.push('# TYPE terrium_batch_avg_execution_time_ms gauge');
    const avgBatchTime = batchMetrics.reduce((a, b) => a + b.averageTimeMs, 0) / batchMetrics.length;
    lines.push(`terrium_batch_avg_execution_time_ms ${avgBatchTime ?? 0} ${timestamp}`);
  }

  return lines.join('\n') + '\n';
}
