/**
 * Batch Job Processor
 *
 * Process multiple simulations in parallel (up to 3 concurrent)
 * with progress tracking and result aggregation.
 *
 * Example:
 *   Run 5 simulations with different Km values
 *   Process 3 at a time, track progress
 *   Aggregate results when all complete
 */

import { logger } from '../logger';
import { describeError } from '../errors';
import ScientificPipeline from '../integration/scientificPipeline';
import { recordBatchMetrics } from '../storage/sweep-batch-metrics';

export interface BatchJob {
  id: string;
  parameters: Record<string, number>;
  label?: string;
}

export interface BatchJobResult {
  jobId: string;
  parameters: Record<string, number>;
  label?: string;
  /**
   * Substrate remaining at the end, or `null` when the job produced none.
   * Never 0 — see ADR 0058.
   */
  finalValue: number | null;
  confidence: number;
  validated: boolean;
  executionTimeMs: number;
  error?: string;
}

export interface BatchProcessResult {
  query: string;
  totalJobs: number;
  completedJobs: number;
  successfulJobs: number;
  failedJobs: number;
  /** Jobs that threw. */
  erroredJobs: number;
  /** Jobs that ran to completion and failed their plausibility checks. */
  didNotValidateJobs: number;
  results: BatchJobResult[];
  totalTimeMs: number;
  successRate: number;
  batchId?: string;
}

/**
 * Process batch jobs with concurrency control
 *
 * Runs up to `concurrency` simulations in parallel
 */
export async function processBatch(
  query: string,
  jobs: BatchJob[],
  concurrency: number = 3,
  onProgress?: (completed: number, total: number) => void
): Promise<BatchProcessResult> {
  const startTime = Date.now();

  logger.info(
    { query, jobCount: jobs.length, concurrency },
    `Starting batch processing (${jobs.length} jobs, concurrency=${concurrency})`
  );

  const results: BatchJobResult[] = [];
  let completedCount = 0;

  /**
   * Process single job
   */
  async function processJob(job: BatchJob): Promise<BatchJobResult> {
    // Declared OUTSIDE the try so the catch can use it. It was inside, so
    // the catch had no start time to subtract and read
    // `Date.now() - Date.now()` — trivially 0. Every failed job therefore
    // reported an execution time of 0ms, including one that had just spent
    // a 120-second timeout getting there. "Failed instantly" and "failed
    // after two minutes" are different diagnoses.
    const jobStartTime = Date.now();

    try {
      const pipeline = new ScientificPipeline();

      const response = await pipeline.execute({
        query,
        parameters: job.parameters
      });

      const executionTimeMs = Date.now() - jobStartTime;

      return {
        jobId: job.id,
        parameters: job.parameters,
        label: job.label,
        // `?? null`, not `|| 0`. See ADR 0058: a placeholder zero wins
        // any comparison scored by smallness, and 0 is also a real result.
        finalValue: response.results?.finalValue ?? null,
        confidence: response.validationConfidence,
        validated: response.validated,
        executionTimeMs
      };
    } catch (error) {
      const executionTimeMs = Date.now() - jobStartTime;
      return {
        jobId: job.id,
        parameters: job.parameters,
        label: job.label,
        finalValue: null,
        confidence: 0,
        validated: false,
        executionTimeMs,
        error: describeError(error)
      };
    }
  }

  /**
   * Process jobs with concurrency control
   */
  async function processWithConcurrency(
    jobList: BatchJob[],
    maxConcurrent: number
  ): Promise<BatchJobResult[]> {
    const output: BatchJobResult[] = [];
    const executing: Promise<void>[] = [];

    for (const job of jobList) {
      // Create promise for this job
      const jobPromise = (async () => {
        const result = await processJob(job);
        output.push(result);
        completedCount++;
        if (onProgress) onProgress(completedCount, jobList.length);
      })();

      executing.push(jobPromise);

      // Wait if we've reached max concurrency
      if (executing.length >= maxConcurrent) {
        await Promise.race(executing);
        executing.splice(executing.findIndex(p => p === jobPromise), 1);
      }
    }

    // Wait for all remaining jobs
    await Promise.all(executing);
    return output;
  }

  const batchResults = await processWithConcurrency(jobs, concurrency);

  /**
   * A job is successful when it RAN AND VALIDATED.
   *
   * This was `!r.error`, which counts only the jobs that threw as failures.
   * A job that ran and did not validate has no `error` string, so it was
   * counted a success — and `scientificPipeline` returns an empty
   * trajectory in exactly that case. A batch of ten jobs where every one
   * failed validation reported `successRate: 100%`.
   *
   * `!error` and `validated` are different facts and neither implies the
   * other: a job can throw (error, not validated) or complete and fail its
   * physical-plausibility checks (no error, not validated). The three
   * counts below are kept separate so a reader can tell which happened.
   */
  const successfulJobs = batchResults.filter(r => r.validated === true).length;
  const erroredJobs = batchResults.filter(r => !!r.error).length;
  const didNotValidateJobs = batchResults.filter(r => !r.error && r.validated !== true).length;
  const failedJobs = erroredJobs + didNotValidateJobs;
  const totalTimeMs = Date.now() - startTime;
  const successRate = successfulJobs / jobs.length;

  logger.info(
    {
      totalJobs: jobs.length,
      successful: successfulJobs,
      failed: failedJobs,
      errored: erroredJobs,
      didNotValidate: didNotValidateJobs,
      successRate: (successRate * 100).toFixed(1),
      totalTimeMs
    },
    'Batch processing complete'
  );

  // Record metrics for the batch operation
  // Map results to validation status for metrics recording
  // `result.validated`, not `!result.error`. The metrics collector's field
  // is named `validated`; feeding it "did not throw" made every
  // /api/metrics/* figure for batches count unvalidated runs as validated.
  const metricsResults = batchResults.map(result => ({
    executionTimeMs: result.executionTimeMs,
    validated: result.validated === true
  }));

  const batchId = `batch_${Date.now()}_${Math.random().toString(36).substring(7)}`;
  recordBatchMetrics(batchId, query, metricsResults);

  logger.info({ batchId }, 'Batch metrics recorded');

  return {
    query,
    totalJobs: jobs.length,
    completedJobs: batchResults.length,
    successfulJobs,
    failedJobs,
    erroredJobs,
    didNotValidateJobs,
    results: batchResults,
    totalTimeMs,
    successRate,
    batchId
  };
}

/**
 * Create batch jobs from parameter values
 *
 * Helper to generate jobs from arrays of values
 */
export function createBatchJobs(
  parameterName: string,
  values: number[],
  baseParameters?: Record<string, number>
): BatchJob[] {
  return values.map((value, index) => ({
    id: `batch_${parameterName}_${index}`,
    parameters: {
      ...baseParameters,
      [parameterName]: value
    },
    label: `${parameterName}=${value}`
  }));
}

/**
 * Create multi-parameter batch jobs
 *
 * More complex: different parameters for each job
 */
export function createMultiParamBatchJobs(
  paramSets: Record<string, number>[],
  baseParameters?: Record<string, number>
): BatchJob[] {
  return paramSets.map((params, index) => ({
    id: `batch_multi_${index}`,
    parameters: {
      ...baseParameters,
      ...params
    },
    label: `Job ${index + 1}`
  }));
}
