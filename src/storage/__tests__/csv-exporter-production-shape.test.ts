/**
 * The job-history CSV, against the object the pipeline actually returns.
 *
 * WHY THIS FILE IS SEPARATE FROM csv-exporter.test.ts
 * ---------------------------------------------------
 * That suite's fixtures are `result: { finalValue, confidence, validated }`.
 * `scientificPipeline.runSimulation` returns nothing of the sort — it
 * returns `{ validated, validationConfidence, results: { finalValue },
 * metadata: { literatureSourcesUsed }, parameterProvenance }`, and
 * `server.ts` stores that verbatim as `job.result`.
 *
 * So the exporter read `job.result.finalValue` and `job.result.confidence`,
 * found neither, and **every real job exported blank cells for both** — for
 * the entire life of `/api/export/jobs/csv`. Twelve tests passed throughout.
 *
 * This is the ADR 0027 blindness: a test that agrees with the code about a
 * question production never asks. The fix for that class is not a better
 * assertion, it is a fixture built from the producer's own return
 * statement. That is what this file is.
 *
 * The fixtures below are transcribed from `scientificPipeline.ts` (the
 * `return` at the end of `runSimulation`). If that shape changes, these
 * tests should be updated from it — not from what makes them pass.
 */
import { exportJobHistoryToCSV } from '../csv-exporter';
import { columnValue } from './csvTestHelpers';

/** Exactly the shape `scientificPipeline.runSimulation` returns. */
function pipelineResponse(overrides: Record<string, any> = {}) {
  return {
    jobId: 'job_real',
    query: 'michaelis-menten',
    validated: true,
    validationConfidence: 0.95,
    validationErrors: [],
    results: {
      trajectory: [{ time: 0, S: 10 }],
      finalValue: 2.34,
      computedMetrics: {},
    },
    reproducibilityKey: 'k',
    dataIntegrityHash: 'h',
    parameterProvenance: {},
    metadata: {
      executionTimeMs: 1,
      literatureSourcesUsed: 0,
      confidenceScore: 0.95,
      warnings: [],
    },
    ...overrides,
  };
}

function storedJob(result: any) {
  return {
    jobId: 'job_real',
    query: 'michaelis-menten',
    status: 'complete',
    startTime: 1,
    endTime: 2,
    duration: 1,
    parameters: { km: 5.2, vmax: 12.8, s0: 10 },
    result,
  };
}

// Quote-aware reading lives in ./csvTestHelpers. The first version of this
// file had its own `line.split(',')`, with a comment claiming every asserted
// column sat before the JSON-quoted `parameters` cell. It does not, and
// three assertions read a fragment of a serialised parameter object instead.
// The helper is shared precisely so that mistake is made once.

describe('the exported job history describes the job that actually ran', () => {
  it('exports the final value, which lives under results', () => {
    // Was blank on every real job. The number is the point of the export.
    const csv = exportJobHistoryToCSV([storedJob(pipelineResponse())]);
    expect(columnValue(csv, 'finalValue')).toBe('2.34');
  });

  it('exports the confidence, which is named validationConfidence', () => {
    const csv = exportJobHistoryToCSV([storedJob(pipelineResponse())]);
    expect(columnValue(csv, 'confidence')).toBe('0.95');
  });

  it('still reads the flat shape used elsewhere in the codebase', () => {
    // /api/compare/jobs and the sweep records use the flat shape. Reading
    // the nested location must not break them.
    const csv = exportJobHistoryToCSV([
      storedJob({ finalValue: 7.5, confidence: 0.5, validated: true }),
    ]);
    expect(columnValue(csv, 'finalValue')).toBe('7.5');
    expect(columnValue(csv, 'confidence')).toBe('0.5');
  });

  it('does not blank a finalValue of zero', () => {
    // Substrate fully consumed is the normal end state of an MM run, so
    // zero is the answer rather than a missing measurement.
    const r = pipelineResponse();
    r.results.finalValue = 0;
    const csv = exportJobHistoryToCSV([storedJob(r)]);
    expect(columnValue(csv, 'finalValue')).toBe('0');
  });
});

describe('the literature column does not claim sources that do not exist', () => {
  it('reports zero sources as zero, not as "yes"', () => {
    // The defect: the column was `validated ? 'yes' : 'no'`, and a run on
    // entirely user-supplied numbers validates fine. A student's hand-typed
    // Km exported as `literatureFound = yes` in the tool whose whole claim
    // is that every number traces to a source.
    const csv = exportJobHistoryToCSV([storedJob(pipelineResponse())], {
      includeLiterature: true,
    });
    expect(columnValue(csv, 'literatureSourcesUsed')).toBe('0');
    expect(csv).not.toContain('literatureFound');
  });

  it('reports a real count when sources were used', () => {
    const r = pipelineResponse();
    r.metadata.literatureSourcesUsed = 4;
    const csv = exportJobHistoryToCSV([storedJob(r)], { includeLiterature: true });
    expect(columnValue(csv, 'literatureSourcesUsed')).toBe('4');
  });

  it('reports "unknown" when nobody looked, never "0"', () => {
    // A record predating the field, or a job that errored before metadata
    // was assembled, did not find zero sources. "Could not check" rendering
    // as "checked, found nothing" is the inversion this project treats as
    // the core defect (three-state discipline, ADR 0037).
    const csv = exportJobHistoryToCSV(
      [storedJob({ validated: true, results: { finalValue: 1 } })],
      { includeLiterature: true },
    );
    expect(columnValue(csv, 'literatureSourcesUsed')).toBe('unknown');
  });

  it('does not derive the literature column from validated', () => {
    // The strongest form of the assertion: two jobs identical in literature
    // (both zero sources) and opposite in `validated` must report the SAME
    // literature value. Any re-derivation from `validated` fails here.
    const passed = pipelineResponse({ validated: true });
    const failed = pipelineResponse({ validated: false });
    const csv = exportJobHistoryToCSV([storedJob(passed), storedJob(failed)], {
      includeLiterature: true,
    });
    expect(columnValue(csv, 'literatureSourcesUsed', 1)).toBe(
      columnValue(csv, 'literatureSourcesUsed', 2),
    );
  });
});
