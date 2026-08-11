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

export async function sensitivityAnalysis(
  query: string,
  baseParameters: Record<string, number>,
  sensitivity: number = 0.1 // 10% perturbation
): Promise<Record<string, { increase: number; decrease: number }>> {
  const results: Record<string, { increase: number; decrease: number }> = {};

  // Get baseline
  const baselinePipeline = new ScientificPipeline();
  const baselineResponse = await baselinePipeline.execute({
    query,
    parameters: baseParameters
  });
  const baselineFinal = baselineResponse.results.finalValue;

  // Test each parameter
  for (const [param, value] of Object.entries(baseParameters)) {
    try {
      // Test with +sensitivity
      const increaseParams = { ...baseParameters };
      increaseParams[param] = value * (1 + sensitivity);
      const increasePipeline = new ScientificPipeline();
      const increaseResponse = await increasePipeline.execute({
        query,
        parameters: increaseParams
      });
      const increaseEffect = Math.abs(increaseResponse.results.finalValue - baselineFinal) / baselineFinal;

      // Test with -sensitivity
      const decreaseParams = { ...baseParameters };
      decreaseParams[param] = value * (1 - sensitivity);
      const decreasePipeline = new ScientificPipeline();
      const decreaseResponse = await decreasePipeline.execute({
        query,
        parameters: decreaseParams
      });
      const decreaseEffect = Math.abs(decreaseResponse.results.finalValue - baselineFinal) / baselineFinal;

      results[param] = {
        increase: increaseEffect,
        decrease: decreaseEffect
      };

      logger.info({ parameter: param, increaseEffect, decreaseEffect }, 'Sensitivity analyzed');
    } catch (error) {
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
