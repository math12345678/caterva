/**
 * Advanced CLI Features for Terrium
 *
 * Additional capabilities:
 * - Batch processing (multiple simulations)
 * - Parameter search (find optimal parameters)
 * - Sensitivity analysis (how parameters affect results)
 * - Data export (CSV, JSON, Excel)
 * - Performance profiling
 */

import ScientificPipeline from '../integration/scientificPipeline';
import { logger } from '../logger';
import * as fs from 'fs';

// ============================================================================
// BATCH PROCESSING
// ============================================================================

export async function batchSimulate(
  scenarios: Array<{
    name: string;
    query: string;
    parameters: Record<string, number>;
  }>
): Promise<Array<{ scenario: string; jobId: string; confidence: number }>> {
  const results: Array<{ scenario: string; jobId: string; confidence: number }> = [];

  for (const scenario of scenarios) {
    try {
      const pipeline = new ScientificPipeline();
      const response = await pipeline.execute({
        query: scenario.query,
        parameters: scenario.parameters
      });

      results.push({
        scenario: scenario.name,
        jobId: response.jobId,
        confidence: response.validationConfidence
      });

      logger.info(
        { scenario: scenario.name, jobId: response.jobId },
        'Batch scenario completed'
      );
    } catch (error) {
      logger.error(
        { scenario: scenario.name, error },
        'Batch scenario failed'
      );
    }
  }

  return results;
}

// ============================================================================
// PARAMETER SEARCH (SIMPLE SWEEP)
// ============================================================================

export async function parameterSweep(
  query: string,
  parameter: string,
  min: number,
  max: number,
  step: number
): Promise<Array<{ paramValue: number; finalValue: number; confidence: number }>> {
  const results: Array<{ paramValue: number; finalValue: number; confidence: number }> = [];

  for (let value = min; value <= max; value += step) {
    try {
      const pipeline = new ScientificPipeline();
      const parameters: Record<string, number> = {};
      parameters[parameter] = value;

      const response = await pipeline.execute({
        query,
        parameters
      });

      if (response.results && response.results.trajectory) {
        const finalValue = response.results.trajectory[response.results.trajectory.length - 1]?.value || 0;
        results.push({
          paramValue: value,
          finalValue,
          confidence: response.validationConfidence
        });
      }

      logger.info(
        { parameter, value, finalValue: response.results.finalValue },
        'Sweep point completed'
      );
    } catch (error) {
      logger.warn(
        { parameter, value, error },
        'Sweep point failed'
      );
    }
  }

  return results;
}

// ============================================================================
// SENSITIVITY ANALYSIS
// ============================================================================

export interface SensitivityEntry {
  /** Relative change in the final value for a +perturbation. */
  increase: number;
  /** ...and for a -perturbation. */
  decrease: number;
  /** The larger of the two: how much the answer rides on this parameter. */
  worst: number;
  /** Set when this parameter could NOT be analysed, with the reason. A
   *  parameter that silently vanished from the results used to be
   *  indistinguishable from one with zero influence. */
  failed?: string;
}

/**
 * How much does the answer depend on each parameter?
 *
 * Perturbs each one by ±`sensitivity` and measures the relative change in
 * the final value. Paired with provenance this answers the question that
 * actually matters to someone using a literature-sourced value: *my Km is
 * a cross-species substitute — does that change my conclusion?* A 40%
 * sensitivity on a cross-species parameter is a result that should not be
 * reported; a 0.1% sensitivity means the substitution is harmless.
 */
export async function sensitivityAnalysis(
  query: string,
  baseParameters: Record<string, number>,
  sensitivity: number = 0.1, // 10% perturbation
  request: Partial<Parameters<ScientificPipeline['execute']>[0]> = {}
): Promise<Record<string, SensitivityEntry>> {
  const results: Record<string, SensitivityEntry> = {};

  // Get baseline
  const baselinePipeline = new ScientificPipeline();
  const baselineResponse = await baselinePipeline.execute({
    ...request,
    query,
    parameters: baseParameters
  });

  // A run that did not validate returns finalValue 0 and an empty
  // trajectory. Dividing by that produced Infinity or NaN for every
  // parameter, which then rendered as a confident-looking sensitivity
  // table for a simulation that never executed.
  if (!baselineResponse.validated) {
    throw new Error(
      'Baseline run did not validate, so there is nothing to perturb: ' +
      baselineResponse.validationErrors.join('; ')
    );
  }

  const baselineFinal = baselineResponse.results.finalValue;
  if (!Number.isFinite(baselineFinal) || baselineFinal === 0) {
    throw new Error(
      `Baseline final value is ${baselineFinal}; a relative sensitivity ` +
      'cannot be computed against it. Choose a shorter window or a larger ' +
      's0 so the substrate is not fully consumed.'
    );
  }

  // Test each parameter
  for (const [param, value] of Object.entries(baseParameters)) {
    try {
      // Test with +sensitivity
      const increaseParams = { ...baseParameters };
      increaseParams[param] = value * (1 + sensitivity);
      const increasePipeline = new ScientificPipeline();
      const increaseResponse = await increasePipeline.execute({
        ...request,
        query,
        parameters: increaseParams
      });
      const increaseEffect = Math.abs(increaseResponse.results.finalValue - baselineFinal) / baselineFinal;

      // Test with -sensitivity
      const decreaseParams = { ...baseParameters };
      decreaseParams[param] = value * (1 - sensitivity);
      const decreasePipeline = new ScientificPipeline();
      const decreaseResponse = await decreasePipeline.execute({
        ...request,
        query,
        parameters: decreaseParams
      });
      const decreaseEffect = Math.abs(decreaseResponse.results.finalValue - baselineFinal) / baselineFinal;

      results[param] = {
        increase: increaseEffect,
        decrease: decreaseEffect,
        worst: Math.max(increaseEffect, decreaseEffect)
      };

      logger.info({ parameter: param, increaseEffect, decreaseEffect }, 'Sensitivity analyzed');
    } catch (error) {
      // RECORDED, not swallowed. This logged a warning and moved on, so a
      // parameter whose analysis failed simply vanished from the table --
      // indistinguishable from one measured to have no influence, which is
      // the opposite conclusion.
      results[param] = {
        increase: Number.NaN,
        decrease: Number.NaN,
        worst: Number.NaN,
        failed: error instanceof Error ? error.message : String(error)
      };
      logger.warn({ parameter: param, error }, 'Sensitivity analysis failed for parameter');
    }
  }

  return results;
}

// ============================================================================
// DATA EXPORT
// ============================================================================

export function exportToCSV(
  results: Array<Record<string, unknown>>,
  filepath: string
): void {
  if (results.length === 0) {
    logger.warn({}, 'No results to export');
    return;
  }

  // Get all unique keys
  const keys = Array.from(
    new Set(results.flatMap(r => Object.keys(r)))
  );

  // Build CSV
  const header = keys.join(',');
  const rows = results.map(r =>
    keys.map(k => {
      const value = r[k];
      if (value === null || value === undefined) return '';
      if (typeof value === 'string' && value.includes(',')) return `"${value}"`;
      return String(value);
    }).join(',')
  );

  const csv = [header, ...rows].join('\n');
  fs.writeFileSync(filepath, csv, 'utf-8');
  logger.info({ filepath }, 'Data exported to CSV');
}

export function exportToJSON(
  data: unknown,
  filepath: string
): void {
  const json = JSON.stringify(data, null, 2);
  fs.writeFileSync(filepath, json, 'utf-8');
  logger.info({ filepath }, 'Data exported to JSON');
}

// ============================================================================
// PERFORMANCE PROFILING
// ============================================================================

export async function profileSimulation(
  query: string,
  parameters: Record<string, number>,
  iterations: number = 5
): Promise<{
  meanTimeMs: number;
  minTimeMs: number;
  maxTimeMs: number;
  stdDevMs: number;
}> {
  const times: number[] = [];

  for (let i = 0; i < iterations; i++) {
    const startTime = Date.now();
    try {
      const pipeline = new ScientificPipeline();
      await pipeline.execute({ query, parameters });
      const endTime = Date.now();
      times.push(endTime - startTime);
    } catch (error) {
      logger.warn({ iteration: i, error }, 'Iteration failed');
    }
  }

  if (times.length === 0) {
    throw new Error('No successful iterations for profiling');
  }

  const meanTimeMs = times.reduce((a, b) => a + b, 0) / times.length;
  const minTimeMs = Math.min(...times);
  const maxTimeMs = Math.max(...times);
  const variance = times.reduce((sum, t) => sum + Math.pow(t - meanTimeMs, 2), 0) / times.length;
  const stdDevMs = Math.sqrt(variance);

  return { meanTimeMs, minTimeMs, maxTimeMs, stdDevMs };
}
