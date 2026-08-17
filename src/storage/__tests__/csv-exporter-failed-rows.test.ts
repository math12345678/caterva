/**
 * How the batch and comparison exports render a row that produced nothing.
 *
 * Both used to write `finalValue: 0` for a failed run. In a column a reader
 * scans for the smallest number — which is how the best model and the best
 * sweep point are both chosen — zero is not a blank. It is the winner.
 *
 * These are the export-side assertions for ADR 0058's engine fixes. The
 * engine now records `null`; this file is about the file that leaves the
 * building actually showing it (ADR 0050).
 */
import { exportBatchToCSV, exportComparisonToCSV } from '../csv-exporter';
import { columnValue, dataLines } from './csvTestHelpers';

const BATCH = {
  results: [
    { parameters: { km: 1 }, finalValue: 4.0, confidence: 0.9, validated: true, executionTimeMs: 12 },
    // Ran to completion, failed its plausibility checks. No `error`.
    { parameters: { km: 2 }, finalValue: 0, confidence: 0, validated: false, executionTimeMs: 11 },
    // Threw.
    { parameters: { km: 3 }, finalValue: null, confidence: 0, validated: false, executionTimeMs: 118, error: 'solver diverged' },
  ],
  summary: {
    totalJobs: 3,
    successfulJobs: 1,
    failedJobs: 2,
    erroredJobs: 1,
    didNotValidateJobs: 1,
    averageExecutionTimeMs: 47,
  },
};

const COMPARISON = {
  models: [
    { model: 'michaelis-menten', finalValue: 4.2, confidence: 0.9, validated: true, executionTimeMs: 10 },
    { model: 'competitive-inhibition', finalValue: 3.9, confidence: 0.9, validated: true, executionTimeMs: 10 },
    { model: 'product-inhibition', finalValue: null, confidence: 0, validated: false, executionTimeMs: 5, error: 'solver diverged' },
  ],
  ranking: ['competitive-inhibition', 'michaelis-menten'],
  bestModel: 'competitive-inhibition',
  modelsAnalyzed: 2,
  modelsExcluded: 1,
  analysis: { meanFinalValue: 4.05, modelVariability: 0.15 },
};

describe('the batch export distinguishes absent from zero', () => {
  it('leaves the finalValue empty for the job that threw', () => {
    const csv = exportBatchToCSV(BATCH);
    const i = dataLines(csv).findIndex(l => l.includes('solver diverged'));
    expect(columnValue(csv, 'finalValue', i)).toBe('');
    expect(columnValue(csv, 'error', i)).toBe('solver diverged');
  });

  it('keeps a genuine zero from a job that ran', () => {
    // The job that did not validate legitimately returned 0. It is still
    // shown — the filtering belongs in the analysis, not in the record of
    // what happened.
    const csv = exportBatchToCSV(BATCH);
    expect(columnValue(csv, 'finalValue', 2)).toBe('0');
    expect(columnValue(csv, 'validated', 2)).toBe('false');
  });

  it('says how many rows produced no usable value, and how they failed', () => {
    const csv = exportBatchToCSV(BATCH);
    expect(csv).toMatch(/2 of 3 job\(s\) produced no usable value/);
    expect(csv).toMatch(/1 failed to run/);
    expect(csv).toMatch(/1 ran but did not pass validation/);
  });

  it('separates the two kinds of failure in the summary', () => {
    // `successfulJobs` counted `!error`, so a job that ran and failed
    // validation was a success. The counts are split so a reader can see
    // which happened.
    const csv = exportBatchToCSV(BATCH);
    expect(csv).toContain('# erroredJobs,1');
    expect(csv).toContain('# didNotValidateJobs,1');
  });

  it('stays quiet when nothing failed', () => {
    // A "0 of 3 failed" banner on every export is noise, and noise is what
    // gets a real warning skipped.
    const csv = exportBatchToCSV({
      results: [{ parameters: {}, finalValue: 1, confidence: 0.9, validated: true, executionTimeMs: 1 }],
      summary: { totalJobs: 1, successfulJobs: 1, failedJobs: 0, averageExecutionTimeMs: 1 },
    });
    expect(csv).not.toMatch(/produced no usable value/);
  });
});

describe('the comparison export shows the model that did not run', () => {
  it('leaves its finalValue empty and names the error', () => {
    const csv = exportComparisonToCSV(COMPARISON);
    const i = dataLines(csv).findIndex(l => l.startsWith('product-inhibition'));
    expect(columnValue(csv, 'finalValue', i)).toBe('');
    expect(columnValue(csv, 'error', i)).toBe('solver diverged');
  });

  it('leaves it unranked rather than ranking it', () => {
    const csv = exportComparisonToCSV(COMPARISON);
    const i = dataLines(csv).findIndex(l => l.startsWith('product-inhibition'));
    expect(columnValue(csv, 'rank', i)).toBe('');
  });

  it('reports how many models the comparison rests on', () => {
    const csv = exportComparisonToCSV(COMPARISON);
    expect(csv).toContain('# modelsAnalyzed,2');
    expect(csv).toContain('# modelsExcluded,1');
  });

  it('states the refusal when no model produced a usable result', () => {
    // `bestModel` is null in that case, and an empty cell beside the label
    // "bestModel" reads as a formatting glitch rather than as the finding.
    // Before the engine fix this branch could not arise at all: the code
    // returned `results[0]` — a model that had just failed — as the winner.
    const csv = exportComparisonToCSV({
      models: [
        { model: 'michaelis-menten', finalValue: null, confidence: 0, validated: false, executionTimeMs: 1, error: 'a' },
        { model: 'competitive-inhibition', finalValue: 0, confidence: 0, validated: false, executionTimeMs: 1 },
      ],
      bestModel: null,
      modelsAnalyzed: 0,
      modelsExcluded: 2,
      analysis: { meanFinalValue: null, modelVariability: null },
      unanalysableReason:
        'None of the 2 model(s) produced a usable result: each either failed to run or did not validate.',
    });

    expect(csv).toContain('# bestModel,\n');
    expect(csv).not.toMatch(/# bestModel,(0|null|michaelis)/);
    expect(csv).toMatch(/None of the 2 model\(s\) produced a usable result/);
    expect(csv).toMatch(/# meanFinalValue,\n/);
  });
});
