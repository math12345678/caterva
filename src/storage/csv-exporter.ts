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
 * Read a result field that lives in a different place in production than it
 * does in this file's test fixtures.
 *
 * `scientificPipeline.runSimulation` returns:
 *
 *     { validated, validationConfidence, results: { finalValue, ... },
 *       parameterProvenance, metadata: { literatureSourcesUsed, ... } }
 *
 * and `server.ts` stores that object verbatim as `job.result`. This file
 * read `job.result.finalValue` and `job.result.confidence` — neither of
 * which exists on that object. **Every real job exported a blank
 * finalValue and a blank confidence**, for as long as the route has
 * existed.
 *
 * The tests did not catch it because their fixtures are
 * `result: { finalValue, confidence, validated }` — a flat shape the
 * pipeline never produces. That is the ADR 0027 blindness exactly: a test
 * that agrees with the code about a question production never asks.
 *
 * Both shapes are read rather than the fixtures being rewritten, because
 * the flat shape is what `/api/compare/jobs` and the sweep records use.
 * The nested location is tried first: it is the one with the real value.
 */
function resultField(result: any, nested: string[], flat: string): any {
  if (!result) return undefined;
  let cursor = result;
  for (const step of nested) {
    if (cursor == null) break;
    cursor = cursor[step];
  }
  return cursor !== undefined && cursor !== null ? cursor : result[flat];
}

/**
 * How many literature sources backed this run — or `unknown`.
 *
 * The column this replaces was named `literatureFound` and its value was
 * `job.result.validated ? 'yes' : 'no'`. `validated` does not mean what
 * that name claims. `scientificCLI.ts` says so in its own comment:
 *
 *     `validated: false` no longer means "unbacked" -- a run on entirely
 *     user-supplied values validates fine and simply scores zero
 *     confidence. It now means the run could not be performed at all.
 *
 * So a simulation run on numbers a student typed in by hand, with no
 * citation anywhere, exported as `literatureFound = yes`. That is a false
 * claim of provenance in the artifact that leaves the building — a
 * sourceless number acquiring borrowed credibility by passing through the
 * tool that promises sources. It is the precise inverse of the
 * `user_cited` discipline, and the more damaging direction of the two.
 *
 * The honest number was one field away the whole time:
 * `metadata.literatureSourcesUsed`.
 *
 * Absent is reported as `unknown`, never as `0`. A record that predates
 * this field, or a job that errored before the metadata was assembled, did
 * not find zero sources — nobody looked. Collapsing those into `0` is the
 * same inversion in miniature: "could not check" must not render as
 * "checked, and there was nothing".
 */
function literatureSourceCount(result: any): string {
  const n = result?.metadata?.literatureSourcesUsed;
  return typeof n === 'number' ? String(n) : 'unknown';
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

  // Renamed from `literatureFound`, deliberately breaking any consumer
  // reading that column. It reported `validated`, which is not literature,
  // and said "yes" for runs with no source at all. A column that makes a
  // false provenance claim is not worth preserving for compatibility;
  // see literatureSourceCount() for the full reasoning.
  if (includeLiterature) {
    headers.push('literatureSourcesUsed');
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
      cell(resultField(job.result, ['results', 'finalValue'], 'finalValue')),
      cell(
        resultField(job.result, ['validationConfidence'], 'confidence') ??
          job.result?.metadata?.confidenceScore,
      ),
      cell(job.result?.validated)
    ];

    if (includeParameters) {
      row.push(escapeCsvField(JSON.stringify(job.parameters || {})));
    }

    if (includeLiterature) {
      row.push(escapeCsvField(literatureSourceCount(job.result)));
    }

    csv += row.join(delimiter) + '\n';
  }

  return csv;
}

/**
 * `#` lines stating how many rows produced no usable value, and why that
 * distinction is visible in the file at all.
 *
 * Shared by the batch and comparison exports. Both used to render a failed
 * row as `finalValue: 0`, which in a column a reader scans for "the
 * smallest number" is not a blank — it is the winner. ADR 0058.
 *
 * Silence when nothing failed: a "0 of 4 failed" line on every export is
 * noise, and noise is what gets a real warning skipped.
 */
function failureSummaryLines(rows: any[], noun: string): string[] {
  const errored = rows.filter(r => !!r.error).length;
  const didNotValidate = rows.filter(r => !r.error && r.validated !== true).length;
  const failed = errored + didNotValidate;

  if (failed === 0) return ['#'];

  const lines = [
    `# ${failed} of ${rows.length} ${noun}(s) produced no usable value.`,
  ];
  if (errored > 0) lines.push(`#   ${errored} failed to run (see the error column).`);
  if (didNotValidate > 0) {
    lines.push(`#   ${didNotValidate} ran but did not pass validation.`);
  }
  lines.push('# Their finalValue cell is EMPTY, not zero. A failure recorded as');
  lines.push('# zero wins any comparison scored by smallness — which is how the');
  lines.push('# best model and the best sweep point are both chosen.');
  lines.push('#');
  return lines;
}

/**
 * `#`-commented provenance lines for a sweep export.
 *
 * Same reasoning as ADR 0050: this file gets opened in Excel, plotted and
 * pasted into a lab report months later, and a plot in a finished report
 * cannot be re-interrogated. `pandas.read_csv(comment="#")` and R's
 * `read.csv(comment.char="#")` skip these; Excel shows them down column A,
 * which is the case that decided it.
 *
 * A sweep needs one thing the trajectory export does not: the distinction
 * between the parameter being **swept** and the parameters holding still.
 * The swept parameter is an experimental condition — the experimenter chose
 * to vary it — so it needs no citation and saying so is more useful than a
 * blank. Everything else is a measured quantity and must carry its source.
 * That is ADR 0012/0013's distinction, applied at the point of export.
 */
function sweepProvenanceHeader(sweepResult: any): string[] {
  const lines: string[] = ['# Terrium parameter sweep'];

  if (sweepResult.query) lines.push(`# query: ${String(sweepResult.query).replace(/\s+/g, ' ')}`);
  if (sweepResult.sweepId) lines.push(`# sweep: ${sweepResult.sweepId}`);
  lines.push('#');

  const swept: any[] = sweepResult.sweptParameters ?? [];
  if (swept.length > 0) {
    lines.push('# SWEPT — chosen by whoever ran this, not resolved from literature');
    for (const p of swept) {
      lines.push(`#   ${p.name}: ${p.min} to ${p.max} step ${p.step}`);
    }
    lines.push('#');
  }

  // Provenance for the parameters held constant. Taken from the first point
  // that carries any: they are held constant, so any point reports the same
  // sources for them. Stated rather than assumed silently.
  const sweptNames = new Set(swept.map((p: any) => p.name));
  const carrier = (sweepResult.results ?? []).find((r: any) => r.parameterProvenance);

  if (carrier) {
    const entries = Object.entries(carrier.parameterProvenance as Record<string, any>)
      .filter(([key]) => !sweptNames.has(key))
      .sort(([a], [b]) => a.localeCompare(b));

    if (entries.length > 0) {
      lines.push('# HELD CONSTANT — and where each value came from');
      for (const [key, prov] of entries) {
        const origin = prov?.origin ?? 'unknown';
        lines.push(`#   ${key} = ${prov?.value ?? '?'}   [${origin}]`);
        if (prov?.citation) lines.push(`#       source: ${String(prov.citation).replace(/\s+/g, ' ')}`);
        if (prov?.organism) lines.push(`#       organism: ${prov.organism}`);
        // A defaulted parameter with a note is the most important line
        // here: the number beside it was not resolved from anything.
        if (prov?.note) lines.push(`#       note: ${String(prov.note).replace(/\s+/g, ' ')}`);
      }
      lines.push('#');
    }
  } else {
    // Absence is spelled out. A reader who saw no provenance block would
    // reasonably assume the sweep did not need one.
    lines.push('# No parameter provenance was recorded for this sweep.');
    lines.push('# That is a gap in the record, not a statement that the');
    lines.push('# values were unsourced.');
    lines.push('#');
  }

  const failed = (sweepResult.results ?? []).filter(
    (r: any) => r.finalValue === null || r.finalValue === undefined || r.validated !== true
  ).length;
  if (failed > 0) {
    lines.push(
      `# ${failed} of ${sweepResult.results.length} point(s) produced no usable value.`,
    );
    lines.push('# They are excluded from the analysis below and their finalValue');
    lines.push('# cell is empty — NOT zero. A crashed point recorded as zero used');
    lines.push('# to win the sweep, because the optimum is the minimum.');
    lines.push('#');
  }

  lines.push('# Lines beginning with # are provenance, not data.');
  lines.push('# pandas: read_csv(path, comment="#")   R: read.csv(path, comment.char="#")');
  lines.push('#');

  return lines;
}

/**
 * Export sweep results as CSV
 */
export function exportSweepToCSV(sweepResult: any, options: ExportOptions = {}): string {
  const { includeParameters = true, delimiter = ',' } = options;

  if (!sweepResult || !sweepResult.results || sweepResult.results.length === 0) {
    return 'No sweep results to export';
  }

  const headers = ['parameterSet', 'finalValue', 'confidence', 'validated', 'error'];

  if (includeParameters) {
    headers.push('parameterDetails');
  }

  let csv = sweepProvenanceHeader(sweepResult).join('\n') + '\n';
  csv += headers.map(escapeCsvField).join(delimiter) + '\n';

  for (const result of sweepResult.results) {
    const row = [
      escapeCsvField(JSON.stringify(result.parameters || {})),
      // `cell` renders null as an empty string, which is what a point that
      // produced no value deserves. It must never render as 0 — see
      // SweepResult.finalValue.
      cell(result.finalValue),
      cell(result.confidence),
      cell(result.validated),
      // Why it produced nothing. An empty finalValue with no explanation is
      // an unexplained absence, which reads as missing data rather than as
      // a run that failed for a stateable reason.
      cell(result.error)
    ];

    if (includeParameters) {
      row.push(escapeCsvField(JSON.stringify(result.parameters || {})));
    }

    csv += row.join(delimiter) + '\n';
  }

  // Add summary statistics
  if (sweepResult.analysis) {
    csv += '\n# Analysis\n';
    // `cell`, not `escapeCsvField`: `analyzeSweep` now returns null for
    // every statistic when no point was analysable, and null must render
    // empty rather than as the string "null" or as 0.
    csv += `# optimalParameters,${cell(
      sweepResult.analysis.optimalParameters === null
        ? undefined
        : JSON.stringify(sweepResult.analysis.optimalParameters)
    )}\n`;
    csv += `# meanFinalValue,${cell(sweepResult.analysis.meanFinalValue)}\n`;
    csv += `# minFinalValue,${cell(sweepResult.analysis.minFinalValue)}\n`;
    csv += `# maxFinalValue,${cell(sweepResult.analysis.maxFinalValue)}\n`;
    csv += `# stdDeviation,${cell(sweepResult.analysis.stdDeviation)}\n`;
    // How much of the grid the numbers above rest on.
    if (sweepResult.analysis.pointsAnalyzed !== undefined) {
      csv += `# pointsAnalyzed,${cell(sweepResult.analysis.pointsAnalyzed)}\n`;
      csv += `# pointsExcluded,${cell(sweepResult.analysis.pointsExcluded)}\n`;
    }
    if (sweepResult.analysis.unanalysableReason) {
      csv += `# ${String(sweepResult.analysis.unanalysableReason).replace(/\s+/g, ' ')}\n`;
    }
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

  // `error` is a column rather than an omission: a blank finalValue with
  // no explanation reads as missing data rather than as a job that failed
  // for a stateable reason.
  const headers = ['jobIndex', 'finalValue', 'confidence', 'validated', 'executionTimeMs', 'error'];

  if (includeParameters) {
    headers.push('parameters');
  }

  let csv = failureSummaryLines(batchResult.results, 'job').join('\n') + '\n';
  csv += headers.map(escapeCsvField).join(delimiter) + '\n';

  for (let i = 0; i < batchResult.results.length; i++) {
    const result = batchResult.results[i];
    const row = [
      escapeCsvField(i + 1),
      // Empty, never 0, for a job that produced no value. See ADR 0058.
      cell(result.finalValue),
      cell(result.confidence),
      cell(result.validated),
      cell(result.executionTimeMs),
      cell(result.error)
    ];

    if (includeParameters) {
      row.push(escapeCsvField(JSON.stringify(result.parameters || {})));
    }

    csv += row.join(delimiter) + '\n';
  }

  // Add summary
  if (batchResult.summary) {
    csv += '\n# Summary\n';
    csv += `# totalJobs,${escapeCsvField(batchResult.summary.totalJobs)}\n`;
    csv += `# successfulJobs,${escapeCsvField(batchResult.summary.successfulJobs)}\n`;
    csv += `# failedJobs,${escapeCsvField(batchResult.summary.failedJobs)}\n`;
    // Split out because "threw" and "ran and did not validate" are
    // different failures with different fixes, and `successfulJobs` used to
    // count the second one as a success.
    if (batchResult.summary.erroredJobs !== undefined) {
      csv += `# erroredJobs,${cell(batchResult.summary.erroredJobs)}\n`;
      csv += `# didNotValidateJobs,${cell(batchResult.summary.didNotValidateJobs)}\n`;
    }
    csv += `# averageExecutionTimeMs,${escapeCsvField(batchResult.summary.averageExecutionTimeMs)}\n`;
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

  const headers = ['model', 'finalValue', 'confidence', 'validated', 'executionTimeMs', 'rank', 'error'];

  let csv = failureSummaryLines(comparisonResult.models, 'model').join('\n') + '\n';
  csv += headers.map(escapeCsvField).join(delimiter) + '\n';

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
      ),
      cell(model.error)
    ];

    csv += row.join(delimiter) + '\n';
  }

  // Add analysis
  if (comparisonResult.analysis) {
    csv += '\n# Analysis\n';
    csv += `# bestModel,${cell(comparisonResult.bestModel)}\n`;
    csv += `# meanFinalValue,${cell(comparisonResult.analysis.meanFinalValue)}\n`;
    csv += `# modelVariability,${cell(comparisonResult.analysis.modelVariability)}\n`;
    if (comparisonResult.modelsAnalyzed !== undefined) {
      csv += `# modelsAnalyzed,${cell(comparisonResult.modelsAnalyzed)}\n`;
      csv += `# modelsExcluded,${cell(comparisonResult.modelsExcluded)}\n`;
    }
  }

  // A refusal has to say it refused. `bestModel` is null when no model
  // produced a usable result, and an empty cell beside the label
  // "bestModel" reads as a formatting glitch rather than as the finding it
  // is. Previously this branch could not arise: the code returned
  // `results[0]` — the first model in the list, which had just failed —
  // as the winner.
  if (comparisonResult.unanalysableReason) {
    csv += `#\n# ${String(comparisonResult.unanalysableReason).replace(/\s+/g, ' ')}\n`;
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
