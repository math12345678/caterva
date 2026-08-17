/**
 * What a batch counts as a success.
 *
 * `successfulJobs` was `batchResults.filter(r => !r.error).length` — jobs
 * that did not throw. A job that ran to completion and failed its
 * physical-plausibility checks has no `error` string, so it was counted a
 * success.
 *
 * `scientificPipeline` returns an empty trajectory in exactly that case. So
 * a batch of ten jobs where every single one failed validation reported
 * `successRate: 100%`, and `/api/metrics/*` recorded them all as validated
 * because the metrics mapper used `validated: !result.error` too.
 *
 * `!error` and `validated` are different facts and neither implies the
 * other. A job can throw, or complete and fail its checks. Collapsing them
 * loses the distinction a reader needs to know which happened.
 */
import { processBatch, createBatchJobs } from '../batch-processor';

const executeMock = jest.fn();

jest.mock('../../integration/scientificPipeline', () => ({
  __esModule: true,
  default: jest.fn().mockImplementation(() => ({
    execute: (...args: any[]) => executeMock(...args),
  })),
}));

jest.mock('../../storage/sweep-batch-metrics', () => ({
  recordBatchMetrics: jest.fn(),
}));

function ranAndValidated(finalValue: number) {
  return {
    validated: true,
    validationConfidence: 0.9,
    results: { trajectory: [{ time: 0 }], finalValue, computedMetrics: {} },
    metadata: { executionTimeMs: 1, literatureSourcesUsed: 1, confidenceScore: 0.9, warnings: [] },
  };
}

/** Ran to completion, failed its plausibility checks. No thrown error. */
function ranAndDidNotValidate() {
  return {
    validated: false,
    validationConfidence: 0,
    results: { trajectory: [], finalValue: 0, computedMetrics: {} },
    metadata: { executionTimeMs: 1, literatureSourcesUsed: 0, confidenceScore: 0, warnings: [] },
  };
}

beforeEach(() => executeMock.mockReset());

describe('a job that did not validate is not a success', () => {
  it('reports 0% success when every job failed validation', async () => {
    // THE DEFECT: this batch reported successRate 1 (100%).
    executeMock.mockImplementation(async () => ranAndDidNotValidate());

    const result = await processBatch('mm', createBatchJobs('km', [1, 2, 3]));

    expect(result.successfulJobs).toBe(0);
    expect(result.successRate).toBe(0);
    expect(result.failedJobs).toBe(3);
  });

  it('distinguishes a job that threw from one that did not validate', async () => {
    // Both are failures, and they are not the same failure. A reader
    // debugging a batch needs to know whether the solver crashed or the
    // result was implausible.
    executeMock.mockImplementation(async ({ parameters }: any) => {
      if (parameters.km === 1) throw new Error('solver diverged');
      if (parameters.km === 2) return ranAndDidNotValidate();
      return ranAndValidated(2.5);
    });

    const result = await processBatch('mm', createBatchJobs('km', [1, 2, 3]));

    expect(result.successfulJobs).toBe(1);
    expect(result.erroredJobs).toBe(1);
    expect(result.didNotValidateJobs).toBe(1);
    expect(result.failedJobs).toBe(2);
  });

  it('records a failed job as absent, not as a finalValue of zero', async () => {
    executeMock.mockImplementation(async () => {
      throw new Error('solver diverged');
    });

    const result = await processBatch('mm', createBatchJobs('km', [1]));

    expect(result.results[0]!.finalValue).toBeNull();
    expect(result.results[0]!.finalValue).not.toBe(0);
    expect(result.results[0]!.error).toBe('solver diverged');
  });

  it('keeps the real message when the pipeline throws a non-Error', async () => {
    // `ScientificPipeline.execute` did not throw an `Error`. It threw a
    // plain object carrying the cause in `message`, and the catch here read
    // `error instanceof Error ? error.message : String(error)` — so every
    // failed job recorded the literal string "[object Object]".
    //
    // The mock above throws `new Error(...)`, which is why the test above
    // passed throughout. Inventing an easier failure shape than the
    // producer's is ADR 0056's lesson applied to the error path: a test can
    // only be as honest as the resemblance between its fixture and its
    // producer, and that applies to how things fail, not just how they
    // succeed.
    //
    // The pipeline now throws a real SimulationError. This asserts the
    // recovery path anyway, because the next `throw { message }` will be
    // written by somebody who has not read src/errors.ts.
    executeMock.mockImplementation(async () => {
      throw {
        jobId: 'job_1',
        error: 'SIMULATION_ERROR',
        message: 'Cannot simulate: km could not be resolved from literature',
        executionTimeMs: 42,
      };
    });

    const result = await processBatch('mm', createBatchJobs('km', [1]));

    expect(result.results[0]!.error).toBe(
      'Cannot simulate: km could not be resolved from literature',
    );
    expect(result.results[0]!.error).not.toBe('[object Object]');
  });

  it('keeps a genuine finalValue of zero', async () => {
    executeMock.mockImplementation(async () => ranAndValidated(0));

    const result = await processBatch('mm', createBatchJobs('km', [1]));

    expect(result.results[0]!.finalValue).toBe(0);
    expect(result.results[0]!.validated).toBe(true);
    expect(result.successfulJobs).toBe(1);
  });

  it('times a failed job rather than reporting 0ms', async () => {
    // `jobStartTime` was declared inside the try, so the catch had nothing
    // to subtract and read `Date.now() - Date.now()`. Every failure
    // reported 0ms, including one that had just spent a 120-second timeout
    // getting there — "failed instantly" and "failed after two minutes"
    // are different diagnoses.
    executeMock.mockImplementation(async () => {
      await new Promise(resolve => setTimeout(resolve, 25));
      throw new Error('slow failure');
    });

    const result = await processBatch('mm', createBatchJobs('km', [1]));

    expect(result.results[0]!.error).toBe('slow failure');
    expect(result.results[0]!.executionTimeMs).toBeGreaterThan(0);
  });
});
