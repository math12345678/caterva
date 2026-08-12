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
import ScientificPipeline from '../integration/scientificPipeline';

export interface BatchJob {
  id: string;
  parameters: Record<string, number>;
  label?: string;
}

export interface BatchJobResult {
  jobId: string;
  parameters: Record<string, number>;
  label?: string;
  finalValue: number;
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
  results: BatchJobResult[];
  totalTimeMs: number;
  successRate: number;
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
    try {
      const jobStartTime = Date.now();
      const pipeline = new ScientificPipeline();

      const response = await pipeline.execute({
        query,
        parameters: job.parameters,
        conditions: { temperature: 37, pH: 7.4 }
      });

      const executionTimeMs = Date.now() - jobStartTime;

      return {
        jobId: job.id,
        parameters: job.parameters,
        label: job.label,
        finalValue: response.results?.finalValue || 0,
        confidence: response.validationConfidence,
        validated: response.validated,
        executionTimeMs
      };
    } catch (error) {
      const executionTimeMs = Date.now() - Date.now();
      return {
        jobId: job.id,
        parameters: job.parameters,
        label: job.label,
        finalValue: 0,
        confidence: 0,
        validated: false,
        executionTimeMs,
        error: error instanceof Error ? error.message : String(error)
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

  const successfulJobs = batchResults.filter(r => !r.error).length;
  const failedJobs = batchResults.filter(r => !!r.error).length;
  const totalTimeMs = Date.now() - startTime;
  const successRate = successfulJobs / jobs.length;

  logger.info(
    {
      totalJobs: jobs.length,
      successful: successfulJobs,
      failed: failedJobs,
      successRate: (successRate * 100).toFixed(1),
      totalTimeMs
    },
    'Batch processing complete'
  );

  return {
    query,
    totalJobs: jobs.length,
    completedJobs: batchResults.length,
    successfulJobs,
    failedJobs,
    results: batchResults,
    totalTimeMs,
    successRate
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
