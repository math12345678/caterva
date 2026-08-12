/**
 * CSV Export Functionality
 *
 * Exports job results and statistics to CSV format
 * Supports: job history, sweep results, batch results, comparison results
 */

export interface ExportOptions {
  includeParameters?: boolean;
  includeLiterature?: boolean;
  delimiter?: string;
}

/**
 * Escape CSV field values (handle quotes and commas)
 */
function escapeCsvField(value: any): string {
  if (value === null || value === undefined) return '';
  const stringValue = String(value);
  if (stringValue.includes(',') || stringValue.includes('"') || stringValue.includes('\n')) {
    return `"${stringValue.replace(/"/g, '""')}"`;
  }
  return stringValue;
}

/**
 * A value that is genuinely absent, as distinct from one that is zero.
 *
 * Every cell in this file was written as `escapeCsvField(x || '')`, and
 * `||` cannot tell "no value" from a falsy value. So a run whose
 * finalValue was **0** exported as an empty cell; so did a confidence of
 * 0, a duration of 0, and `validated: false` — which is not missing data,
 * it is the most important thing on the row.
 *
 * A substrate fully consumed (s0 → 0) is the normal end state of a
 * Michaelis-Menten run, so this is not an edge case: it is the answer,
 * blanked. And a blank cell reads as "we did not measure this" rather than
 * "we measured this and it was zero" — two claims a reader would act on
 * very differently.
 *
 * Same defect class as the `km || 5.2` defaults ADR 0012/0013 forbid, in
 * the direction of erasure rather than invention.
 */
function cell(value: any): string {
  return value === null || value === undefined ? '' : escapeCsvField(value);
}

/**
 * Export job history as CSV
 */
export function exportJobHistoryToCSV(jobs: any[], options: ExportOptions = {}): string {
  const { includeParameters = true, includeLiterature = false, delimiter = ',' } = options;

  if (jobs.length === 0) {
    return 'No jobs to export';
  }

  // Build header
  const headers = ['jobId', 'query', 'status', 'startTime', 'endTime', 'durationMs', 'finalValue', 'confidence', 'validated'];

  if (includeParameters) {
    headers.push('parameters');
  }

  if (includeLiterature) {
    headers.push('literatureFound');
  }

  let csv = headers.map(escapeCsvField).join(delimiter) + '\n';

  // Add rows
  for (const job of jobs) {
    const row = [
      escapeCsvField(job.jobId),
      escapeCsvField(job.query),
      escapeCsvField(job.status),
      escapeCsvField(job.startTime ? new Date(job.startTime).toISOString() : ''),
      escapeCsvField(job.endTime ? new Date(job.endTime).toISOString() : ''),
      cell(job.duration),
      cell(job.result?.finalValue),
      cell(job.result?.confidence),
      cell(job.result?.validated)
    ];

    if (includeParameters) {
      row.push(escapeCsvField(JSON.stringify(job.parameters || {})));
    }

    if (includeLiterature) {
      row.push(escapeCsvField((job.result?.validated || false) ? 'yes' : 'no'));
    }

    csv += row.join(delimiter) + '\n';
  }

  return csv;
}

/**
 * Export sweep results as CSV
 */
export function exportSweepToCSV(sweepResult: any, options: ExportOptions = {}): string {
  const { includeParameters = true, delimiter = ',' } = options;

  if (!sweepResult || !sweepResult.results || sweepResult.results.length === 0) {
    return 'No sweep results to export';
  }

  const headers = ['parameterSet', 'finalValue', 'confidence', 'validated'];

  if (includeParameters) {
    headers.push('parameterDetails');
  }

  let csv = headers.map(escapeCsvField).join(delimiter) + '\n';

  for (const result of sweepResult.results) {
    const row = [
      escapeCsvField(JSON.stringify(result.parameters || {})),
      cell(result.finalValue),
      cell(result.confidence),
      cell(result.validated)
    ];

    if (includeParameters) {
      row.push(escapeCsvField(JSON.stringify(result.parameters || {})));
    }

    csv += row.join(delimiter) + '\n';
  }

  // Add summary statistics
  if (sweepResult.analysis) {
    csv += '\n# Analysis\n';
    csv += `optimalParameters,${escapeCsvField(JSON.stringify(sweepResult.analysis.optimalParameters))}\n`;
    csv += `meanFinalValue,${escapeCsvField(sweepResult.analysis.meanFinalValue)}\n`;
    csv += `minFinalValue,${escapeCsvField(sweepResult.analysis.minFinalValue)}\n`;
    csv += `maxFinalValue,${escapeCsvField(sweepResult.analysis.maxFinalValue)}\n`;
    csv += `stdDeviation,${escapeCsvField(sweepResult.analysis.stdDeviation)}\n`;
  }

  return csv;
}

/**
 * Export batch results as CSV
 */
export function exportBatchToCSV(batchResult: any, options: ExportOptions = {}): string {
  const { includeParameters = true, delimiter = ',' } = options;

  if (!batchResult || !batchResult.results || batchResult.results.length === 0) {
    return 'No batch results to export';
  }

  const headers = ['jobIndex', 'finalValue', 'confidence', 'validated', 'executionTimeMs'];

  if (includeParameters) {
    headers.push('parameters');
  }

  let csv = headers.map(escapeCsvField).join(delimiter) + '\n';

  for (let i = 0; i < batchResult.results.length; i++) {
    const result = batchResult.results[i];
    const row = [
      escapeCsvField(i + 1),
      cell(result.finalValue),
      cell(result.confidence),
      cell(result.validated),
      cell(result.executionTimeMs)
    ];

    if (includeParameters) {
      row.push(escapeCsvField(JSON.stringify(result.parameters || {})));
    }

    csv += row.join(delimiter) + '\n';
  }

  // Add summary
  if (batchResult.summary) {
    csv += '\n# Summary\n';
    csv += `totalJobs,${escapeCsvField(batchResult.summary.totalJobs)}\n`;
    csv += `successfulJobs,${escapeCsvField(batchResult.summary.successfulJobs)}\n`;
    csv += `failedJobs,${escapeCsvField(batchResult.summary.failedJobs)}\n`;
    csv += `averageExecutionTimeMs,${escapeCsvField(batchResult.summary.averageExecutionTimeMs)}\n`;
  }

  return csv;
}

/**
 * Export model comparison results as CSV
 */
export function exportComparisonToCSV(comparisonResult: any, options: ExportOptions = {}): string {
  const { delimiter = ',' } = options;

  if (!comparisonResult || !comparisonResult.models || comparisonResult.models.length === 0) {
    return 'No comparison results to export';
  }

  const headers = ['model', 'finalValue', 'confidence', 'validated', 'executionTimeMs', 'rank'];

  let csv = headers.map(escapeCsvField).join(delimiter) + '\n';

  for (let i = 0; i < comparisonResult.models.length; i++) {
    const model = comparisonResult.models[i];
    const row = [
      cell(model.model),
      cell(model.finalValue),
      cell(model.confidence),
      cell(model.validated),
      cell(model.executionTimeMs),
      // `ranking?.indexOf(x) + 1` is NaN when `ranking` is absent, and -1+1
      // = 0 when the model is not in it. Neither is a rank; both used to be
      // hidden by the `|| ''` this replaced, so the blank cell was right by
      // accident. Stated explicitly now: a missing rank is missing, and an
      // unranked model is not silently promoted to rank 0.
      cell(
        (() => {
          const position = comparisonResult.ranking?.indexOf(model.model);
          return position === undefined || position < 0 ? undefined : position + 1;
        })()
      )
    ];

    csv += row.join(delimiter) + '\n';
  }

  // Add analysis
  if (comparisonResult.analysis) {
    csv += '\n# Analysis\n';
    csv += `bestModel,${escapeCsvField(comparisonResult.bestModel)}\n`;
    csv += `meanFinalValue,${escapeCsvField(comparisonResult.analysis.meanFinalValue)}\n`;
    csv += `modelVariability,${escapeCsvField(comparisonResult.analysis.modelVariability)}\n`;
  }

  return csv;
}

/**
 * Export statistics as CSV
 */
export function exportStatisticsToCSV(stats: any, delimiter = ','): string {
  let csv = 'Metric,Value\n';

  csv += `totalJobs,${escapeCsvField(stats.totalJobs)}\n`;
  csv += `successfulJobs,${escapeCsvField(stats.successful)}\n`;
  csv += `failedJobs,${escapeCsvField(stats.failed)}\n`;
  csv += `averageExecutionTimeMs,${escapeCsvField(stats.averageExecutionTimeMs)}\n`;

  if (stats.queryCounts) {
    csv += '\n# Query Distribution\n';
    for (const [query, count] of Object.entries(stats.queryCounts)) {
      csv += `${escapeCsvField(query)},${escapeCsvField(count)}\n`;
    }
  }

  return csv;
}
